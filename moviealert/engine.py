"""Turn fetched shows into alert events for one watch. Pure: no I/O.

Per-watch state (JSON-serialisable dict):
    initialized : bool            first evaluation done (baseline, no calls)
    open        : [okey, ...]     "<provider>:<cinema_id>" already announced
    avail       : {skey: int}     "<provider>:<cinema_id>:<sid>" -> seats seen
    last_call   : epoch seconds
"""

import re
from typing import Dict, List, Optional, Tuple

from .config import TheatreGroup, Watch
from .models import Event, Show


def group_for(watch: Watch, show: Show) -> Optional[TheatreGroup]:
    for g in watch.groups:
        if show.provider not in g.sources:
            continue
        if re.search(g.match, show.cinema, re.I):
            return g
    return None


def show_ok(watch: Watch, g: TheatreGroup, s: Show) -> bool:
    if not s.detail:
        return True  # provider has no format/language data (BMS)
    if watch.language and watch.language.lower() not in s.lang.lower():
        return False
    for f in watch.formats:
        if f.lower() not in s.fmt.lower():
            return False
    if g.format_match and not re.search(g.format_match, s.fmt, re.I):
        return False
    return True


def in_window(watch: Watch, s: Show) -> bool:
    if not s.time:
        return True
    if watch.show_from and s.time < watch.show_from:
        return False
    if watch.show_to and s.time > watch.show_to:
        return False
    return True


def evaluate(
    watch: Watch,
    shows: Dict[str, Optional[List[Show]]],
    ws: dict,
) -> Tuple[List[Event], List[str], dict]:
    """shows: provider -> list of Show, or None when that provider wasn't
    fetched this round (failed or throttled). Returns (events, snapshot, new_ws)."""
    first_run = not ws.get("initialized")
    prev_open = set(ws.get("open", []))
    seen_open = set(prev_open)
    prev_avail = ws.get("avail", {})
    avail = dict(prev_avail)
    need = watch.min_seats
    events: List[Event] = []
    snapshot: List[str] = []

    for provider, plist in shows.items():
        if plist is None:
            continue  # keep previous knowledge for this provider
        avail = {k: v for k, v in avail.items() if not k.startswith(provider + ":")}

        by_cinema: Dict[Tuple[str, str], Tuple[TheatreGroup, List[Show]]] = {}
        for s in plist:
            g = group_for(watch, s)
            if not g or not show_ok(watch, g, s):
                continue
            by_cinema.setdefault((s.cinema_id, s.cinema), (g, []))[1].append(s)

        for (cid, cname), (g, ss) in by_cinema.items():
            okey = f"{provider}:{cid}"
            label = "District" if provider == "district" else "BookMyShow"
            detailed = [x for x in ss if x.detail]
            if detailed:
                detailed.sort(key=lambda x: x.time or "")
                listing = ", ".join(f"{x.time_text} ({x.avail} left)" for x in detailed)
                snapshot.append(f"[{label}] {cname}: {listing}")
                if g.alert_on_open and okey not in seen_open:
                    events.append(Event(0, f"OPENED on {label}: {cname}\n  {detailed[0].fmt} | {listing}"))
            else:
                snapshot.append(f"[{label}] {cname} ({cid}) is listing {watch.date}")
                if g.alert_on_open and okey not in seen_open:
                    events.append(Event(0, f"OPENED on {label}: {cname} ({cid}) for {watch.date}"))
            seen_open.add(okey)

            for x in detailed:
                k = f"{provider}:{cid}:{x.sid}"
                avail[k] = x.avail
                if not g.alert_on_seats or not in_window(watch, x):
                    continue
                before = prev_avail.get(k)
                fire = x.avail >= need and (
                    # brand-new show at a cinema we already knew about
                    (before is None and not first_run and okey in prev_open)
                    # went from "not enough" to "enough"
                    or (before is not None and before < need)
                    # a batch of seats was released
                    or (before is not None and x.avail - before >= need)
                )
                if fire:
                    areas = ", ".join(f"{a[0]} {a[1]}" for a in x.areas)
                    events.append(Event(1, f"SEATS BACK on {label}: {cname} {x.time_text} "
                                           f"{x.fmt} -> {x.avail} seats ({areas})"))

    new_ws = {
        "initialized": True,
        "open": sorted(seen_open),
        "avail": avail,
        "last_call": ws.get("last_call", 0),
    }
    if first_run:
        events = []  # baseline: don't alert on what was already true
    events.sort(key=lambda e: e.priority)
    return events, snapshot, new_ws
