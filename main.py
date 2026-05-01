import os
from datetime import date, timedelta

import paho.mqtt.publish as mqtt_publish
import requests
from dotenv import load_dotenv
from icalendar import Calendar

load_dotenv()

ICS_URL = os.environ["ICS_URL"]
MQTT_HOSTNAME = os.environ["MQTT_HOSTNAME"]
MQTT_TOPIC = os.environ["MQTT_TOPIC"]
MQTT_USERNMAE = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")

# RGB hex colors per container type (X-SRH-CONTAINER-TYPE field)
CONTAINER_COLORS: dict[str, str] = {
    "yellow": "#FFFF00",  # gelbe Wertstofftonne / gelber Sack
    "black": "#FF0000",  # rote/schwarze Restmülltonne
    "green": "#00AA00",  # grüne Biotonne
    "blue": "#0000FF",  # blaue Papiertonne
    "grey": "#808080",  # alternative grey spelling
    "gray": "#808080",
}

DEFAULT_COLOR = "#FFFFFF"


def fetch_calendar(url: str) -> Calendar:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return Calendar.from_ical(response.content)


def get_tomorrows_pickups(calendar: Calendar) -> list[dict]:
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
            container_type = str(component.get("X-SRH-CONTAINER-TYPE", "")).lower()
            summary = str(component.get("SUMMARY", "Unknown"))
            pickups.append({"type": container_type, "summary": summary})
    return pickups


def type_to_color(container_type: str) -> str:
    return CONTAINER_COLORS.get(container_type, DEFAULT_COLOR)


def send_mqtt(hostname: str, topic: str, color_hex: str) -> None:
    payload = color_hex.lstrip("#").upper()
    mqtt_publish.single(topic, payload=payload, hostname=hostname)
    print(f"Published to {topic}: {payload}")


def main() -> None:
    print("Fetching Abholtermine …")
    calendar = fetch_calendar(ICS_URL)

    pickups = get_tomorrows_pickups(calendar)
    if not pickups:
        print("No Abholtermine tomorrow.")
        return

    print(f"Abholtermine tomorrow ({date.today() + timedelta(days=1)}):")
    for pickup in pickups:
        color = type_to_color(pickup["type"])
        print(f"  {pickup['summary']} (type={pickup['type']!r}) → {color}")
        send_mqtt(MQTT_HOSTNAME, MQTT_TOPIC, color)


if __name__ == "__main__":
    main()
