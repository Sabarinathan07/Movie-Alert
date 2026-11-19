"""BookMyShow provider.

The buytickets page lists a venue link .../buytickets/<CODE>/<YYYYMMDD> only
for venues with live shows on that exact date, so a fallback page (BMS shows
the nearest open date when ours isn't open) can't produce false positives.
No format / seat data is exposed, so shows come back with detail=False.
"""

import re

from ..models import Show
from .http import fetch


def parse(html, date):
    ymd = date.replace("-", "")
    venues = {}
    for slug, code in re.findall(
        r"/cinemas/[a-z-]+/([a-z0-9-]+)/buytickets/([A-Z0-9]+)/" + ymd, html
    ):
        venues[code] = slug
    return [
        Show(provider="bms", cinema_id=code, cinema=slug.replace("-", " "), detail=False)
        for code, slug in venues.items()
    ]


def fetch_shows(url, date):
    return parse(fetch(url, warmup="https://in.bookmyshow.com/"), date)
