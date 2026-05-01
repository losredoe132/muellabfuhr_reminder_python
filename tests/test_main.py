from datetime import date, datetime, timezone
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest
from icalendar import Calendar

import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ics(events: list[dict]) -> bytes:
    """Build a minimal ICS byte string from a list of event dicts."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:Test//Test//DE",
    ]
    for ev in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev.get('uid', 'test-uid')}",
            f"SUMMARY:{ev.get('summary', 'Test')}",
            f"DTSTART;VALUE=DATE:{ev['dtstart']}",
            f"DTEND;VALUE=DATE:{ev['dtend']}",
        ]
        if "container_type" in ev:
            lines.append(f"X-SRH-CONTAINER-TYPE:{ev['container_type']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode()


# ---------------------------------------------------------------------------
# type_to_color
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "container_type, expected_color",
    [
        ("yellow", "#FFFF00"),
        ("black", "#808080"),
        ("green", "#00AA00"),
        ("blue", "#0000FF"),
        ("grey", "#808080"),
        ("gray", "#808080"),
        ("unknown", "#FFFFFF"),  # fallback
        ("", "#FFFFFF"),  # empty string fallback
    ],
)
def test_type_to_color(container_type, expected_color):
    assert main.type_to_color(container_type) == expected_color


# ---------------------------------------------------------------------------
# get_tomorrows_pickups
# ---------------------------------------------------------------------------


def test_get_tomorrows_pickups_finds_event():
    tomorrow = date(2026, 5, 6)
    ics = _make_ics(
        [
            {
                "uid": "ev1",
                "summary": "Abfuhr gelbe Wertstofftonne/-sack",
                "dtstart": "20260506",
                "dtend": "20260507",
                "container_type": "yellow",
            }
        ]
    )
    cal = Calendar.from_ical(ics)
    with patch("main.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 5)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        pickups = main.get_tomorrows_pickups(cal)

    assert len(pickups) == 1
    assert pickups[0]["type"] == "yellow"
    assert pickups[0]["summary"] == "Abfuhr gelbe Wertstofftonne/-sack"


def test_get_tomorrows_pickups_no_event_today():
    ics = _make_ics(
        [
            {
                "uid": "ev1",
                "summary": "Abfuhr schwarze Restmülltonne",
                "dtstart": "20260510",
                "dtend": "20260511",
                "container_type": "black",
            }
        ]
    )
    cal = Calendar.from_ical(ics)
    with patch("main.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 5)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        pickups = main.get_tomorrows_pickups(cal)

    assert pickups == []


def test_get_tomorrows_pickups_multiple_events():
    ics = _make_ics(
        [
            {
                "uid": "ev1",
                "summary": "Abfuhr gelbe Wertstofftonne/-sack",
                "dtstart": "20260506",
                "dtend": "20260507",
                "container_type": "yellow",
            },
            {
                "uid": "ev2",
                "summary": "Abfuhr grüne Biotonne",
                "dtstart": "20260506",
                "dtend": "20260507",
                "container_type": "green",
            },
            {
                "uid": "ev3",
                "summary": "Abfuhr schwarze Restmülltonne",
                "dtstart": "20260513",
                "dtend": "20260514",
                "container_type": "black",
            },
        ]
    )
    cal = Calendar.from_ical(ics)
    with patch("main.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 5)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        pickups = main.get_tomorrows_pickups(cal)

    types = {p["type"] for p in pickups}
    assert types == {"yellow", "green"}


def test_get_tomorrows_pickups_missing_container_type():
    """Events without X-SRH-CONTAINER-TYPE should still be returned with empty type."""
    ics = _make_ics(
        [
            {
                "uid": "ev1",
                "summary": "Unbekannte Abholung",
                "dtstart": "20260506",
                "dtend": "20260507",
            }
        ]
    )
    cal = Calendar.from_ical(ics)
    with patch("main.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 5)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        pickups = main.get_tomorrows_pickups(cal)

    assert len(pickups) == 1
    assert pickups[0]["type"] == ""


# ---------------------------------------------------------------------------
# fetch_calendar
# ---------------------------------------------------------------------------


def test_fetch_calendar_parses_response():
    ics_bytes = _make_ics(
        [
            {
                "uid": "ev1",
                "summary": "Test",
                "dtstart": "20260506",
                "dtend": "20260507",
                "container_type": "yellow",
            }
        ]
    )
    mock_response = MagicMock()
    mock_response.content = ics_bytes
    mock_response.raise_for_status = MagicMock()

    with patch("main.requests.get", return_value=mock_response) as mock_get:
        cal = main.fetch_calendar("http://test.example/cal.ics")

    mock_get.assert_called_once_with("http://test.example/cal.ics", timeout=15)
    mock_response.raise_for_status.assert_called_once()
    assert isinstance(cal, Calendar)


# ---------------------------------------------------------------------------
# send_mqtt
# ---------------------------------------------------------------------------


def test_send_mqtt_publishes_correct_payload():
    with patch("main.mqtt_publish.single") as mock_single:
        main.send_mqtt("broker.local", "wled/c1b27c", "#FFFF00")
        mock_single.assert_called_once_with(
            "wled/c1b27c", payload="FFFF00", hostname="broker.local"
        )


def test_send_mqtt_strips_hash_and_uppercases():
    with patch("main.mqtt_publish.single") as mock_single:
        main.send_mqtt("localhost", "wled/c1b27c", "#00aa00")
        args, kwargs = mock_single.call_args
        assert kwargs["payload"] == "00AA00"
