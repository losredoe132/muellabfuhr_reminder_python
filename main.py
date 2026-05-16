import logging
import os

import coloredlogs
from dataclasses import dataclass
from datetime import date, timedelta
from enum import IntEnum

import requests
from dotenv import load_dotenv
from icalendar import Calendar
from typing import NamedTuple

load_dotenv()

logger = logging.getLogger(__name__)
coloredlogs.install(level=logging.INFO, logger=logger)

ICS_URL = os.environ["ICS_URL"]
HA_URL = os.getenv("HASS_IP")
HA_URL_LIGHT = HA_URL+"/api/services/light/"

TOKEN = os.getenv("HASS_LLT")
HASS_ENTITY_ID = os.getenv("HASS_ENTITY_ID")

class PickupType(IntEnum):
    WERTSTOFF = 1
    RESTMUELL = 2
    BIO = 3
    PAPIER = 4
    GRAU = 5
    UNBEKANNT = 0

class RGBColor(NamedTuple):
    r: int
    g: int
    b: int

    @property
    def is_on(self) -> bool:
        return self.r > 0 or self.g > 0 or self.b > 0


PICKUP_TYPE_BY_NAME: dict[str, PickupType] = {
    "yellow": PickupType.WERTSTOFF,
    "black": PickupType.RESTMUELL,
    "green": PickupType.BIO,
    "blue": PickupType.PAPIER,
    "grey": PickupType.GRAU,
    "unknown": PickupType.UNBEKANNT,
}


# RGB colors per container type
CONTAINER_COLORS: dict[PickupType, RGBColor] = {
    PickupType.WERTSTOFF: RGBColor(255, 255, 0),    # gelbe Wertstofftonne / gelber Sack
    PickupType.RESTMUELL: RGBColor(255, 0, 0),      # rote/schwarze Restmülltonne
    PickupType.BIO: RGBColor(0, 170, 0),            # grüne Biotonne
    PickupType.PAPIER: RGBColor(0, 0, 255),         # blaue Papiertonne
    PickupType.UNBEKANNT: RGBColor(255, 0, 251),
}

DEFAULT_COLOR = RGBColor(0, 0, 0)


@dataclass
class Pickup:
    type: PickupType
    summary: str


def fetch_calendar(url: str) -> Calendar:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return Calendar.from_ical(response.content)


def get_tomorrows_pickups(calendar: Calendar) -> list[Pickup]:
    tomorrow = date.today() + timedelta(days=1)
    pickups = []
    for component in calendar.walk():
        if component.name != "VEVENT":
            continue
        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue
        event_date = dtstart.dt
        if hasattr(event_date, "date"):
            event_date = event_date.date()
        if event_date == tomorrow:
            raw = str(component.get("X-SRH-CONTAINER-TYPE", "")).lower()
            if raw == "gray":
                raw = "grey"
            pickup_type = PICKUP_TYPE_BY_NAME.get(raw, PickupType.UNBEKANNT)
            summary = str(component.get("SUMMARY", "Unknown"))
            pickups.append(Pickup(type=pickup_type, summary=summary))
    return pickups


def type_to_color(pickup_type: PickupType) -> RGBColor:
    return CONTAINER_COLORS.get(pickup_type, DEFAULT_COLOR)


def send_color(color_rgb: RGBColor) -> None:
    
    headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        }

    if color_rgb.is_on:
        url = HA_URL_LIGHT + "turn_on"
        data = {
            "entity_id": HASS_ENTITY_ID,
            "rgb_color": color_rgb,
        }
    else:
        url = HA_URL_LIGHT + "turn_off"
        data = {
            "entity_id": HASS_ENTITY_ID,
        }

    logger.info("Post to HA: %s with data %s", url, data)
    response = requests.post(url, headers=headers, json=data)
    

    logger.info("HA response: %s", response.status_code)
    if response.status_code != 200:
        logger.error("Failed to send color to Home Assistant: %s", response.text)

def main() -> None:

    logger.info("Fetching Abholtermine …")
    calendar = fetch_calendar(ICS_URL)

    pickups = get_tomorrows_pickups(calendar)
    if len(pickups) == 0:
        logger.info("No Abholtermine tomorrow.")
        send_color(DEFAULT_COLOR)
    else:
        logger.info("Abholtermine tomorrow (%s):", date.today() + timedelta(days=1))
        for pickup in pickups:
            color = type_to_color(pickup.type)
            logger.info("  %s (type=%r) → %s", pickup.summary, pickup.type, color)
            send_color(color)


if __name__ == "__main__":
    main()
