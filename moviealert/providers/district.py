"""District (district.in) provider.

The public movie page embeds every cinema's sessions for the requested date in
__NEXT_DATA__, including screen format, language and seats available/total.
"""

import json
import re

from ..models import Show
from .http import fetch


def parse(html, date):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("District: __NEXT_DATA__ not found (page layout changed?)")
    data = json.loads(m.group(1))
    ms = (
        data.get("props", {}).get("pageProps", {}).get("data", {})
        .get("serverState", {}).get("movieSessions", {})
    )
    out = []
    for entry in ms.values():
        # District silently falls back to the nearest open date; ignore that.
        if entry.get("searchDate") != date:
            continue
        pd = entry.get("pageData", {}) or {}
        for cinema in (pd.get("nearbyCinemas") or []) + (pd.get("farCinemas") or []):
            name = (cinema.get("cinemaInfo") or {}).get("name") or ""
            for s in cinema.get("sessions") or []:
                if s.get("showDate") and s["showDate"] != date:
                    continue
                out.append(Show(
                    provider="district",
                    cinema_id=str(cinema.get("id")),
                    cinema=name,
                    sid=str(s.get("sid")),
                    time=(s.get("showTimeISO") or "")[11:16] or None,
                    time_text=s.get("showTimeText") or "",
                    fmt=s.get("scrnFmt") or "",
                    lang=s.get("lang") or "",
                    avail=int(s.get("avail") or 0),
                    total=int(s.get("total") or 0),
                    areas=[(a.get("label"), a.get("sAvail"), a.get("price"))
                           for a in s.get("areas") or []],
                ))
    return out


def fetch_shows(url, date):
    html = fetch(url, direct_ok=lambda t: "__NEXT_DATA__" in t)
    return parse(html, date)
