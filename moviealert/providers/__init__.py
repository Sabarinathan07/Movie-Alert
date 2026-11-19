"""Ticketing providers. Each module exposes fetch_shows(url, date) -> list[Show]."""

from . import bms, district

REGISTRY = {
    "district": district.fetch_shows,
    "bms": bms.fetch_shows,
}
