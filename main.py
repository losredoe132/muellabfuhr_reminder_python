import os
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

import paho.mqtt.publish as mqtt_publish
import requests
from dotenv import load_dotenv
from icalendar import Calendar

load_dotenv()

ICS_URL = os.environ["ICS_URL"]
MQTT_HOSTNAME = os.environ["MQTT_HOSTNAME"]
MQTT_TOPIC = os.environ["MQTT_TOPIC"]
MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")


class PickupType(str, Enum):
    WERTSTOFF = "yellow"
    RESTMUELL = "black"
    BIO = "green"
    PAPIER = "blue"
    GRAU = "grey"
    UNBEKANNT = "unknown"


# RGB hex colors per container type
CONTAINER_COLORS: dict[PickupType, str] = {
    PickupType.WERTSTOFF: "#FFFF00",  # gelbe Wertstofftonne / gelber Sack
    PickupType.RESTMUELL: "#FF0000",  # rote/schwarze Restmülltonne
    PickupType.BIO: "#00AA00",  # grüne Biotonne
    PickupType.PAPIER: "#0000FF",  # blaue Papiertonne
    PickupType.UNBEKANNT: "#FF00FB",
}

DEFAULT_COLOR = "#000000"


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
            try:
                pickup_type = PickupType(raw)
            except ValueError:
                pickup_type = PickupType.UNBEKANNT
            summary = str(component.get("SUMMARY", "Unknown"))
            pickups.append(Pickup(type=pickup_type, summary=summary))
    return pickups


def type_to_color(pickup_type: PickupType) -> str:
    return CONTAINER_COLORS.get(pickup_type, DEFAULT_COLOR)


def send_mqtt_color(color_hex: str) -> None:
    payload = color_hex
    mqtt_publish.single(
        MQTT_TOPIC + "/col",
        payload=payload,
        hostname=MQTT_HOSTNAME,
        auth={"username": MQTT_USERNAME, "password": MQTT_PASSWORD}
        if MQTT_USERNAME
        else None,
    )
    print(f"Published to {MQTT_TOPIC}: {payload}")


def main() -> None:
    print("Fetching Abholtermine …")
    calendar = fetch_calendar(ICS_URL)

    pickups = get_tomorrows_pickups(calendar)
    if not pickups:
        print("No Abholtermine tomorrow.")
        send_mqtt_color(DEFAULT_COLOR)

    print(f"Abholtermine tomorrow ({date.today() + timedelta(days=1)}):")
    for pickup in pickups:
        color = type_to_color(pickup.type)
        print(f"  {pickup.summary} (type={pickup.type!r}) → {color}")
        send_mqtt_color(color)


if __name__ == "__main__":
    main()
