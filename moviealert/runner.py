"""One polling round: fetch each distinct page once, fan out to every watch.

State file layout (v2):
    {"version": 2,
     "fetch":   {"<provider>|<url>": last_fetch_epoch},
     "watches": {"<watch id>": <engine per-watch state>}}
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import notify
from .config import Config, Watch
from .engine import evaluate
from .models import Show
from .providers import REGISTRY


def load_state(path: Path, cfg: Config) -> dict:
    try:
        st = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"version": 2, "fetch": {}, "watches": {}}
    if st.get("version") == 2:
        return st
    # v1 (single-watch watcher.py) -> v2: adopt it as the first watch's state
    # so upgrading doesn't re-alert on everything already seen.
    first = cfg.watches[0].id if cfg.watches else "default"
    ws = {k: st[k] for k in ("initialized", "open", "avail", "last_call") if k in st}
    fetch = {}
    if st.get("last_bms") and cfg.watches:
        for s in cfg.watches[0].sources:
            if s.provider == "bms":
                fetch[f"bms|{s.url_for(cfg.watches[0].date)}"] = st["last_bms"]
    return {"version": 2, "fetch": fetch, "watches": {first: ws}}


def save_state(path: Path, st: dict):
    path.write_text(json.dumps(st, indent=2, sort_keys=True))


def fetch_all(cfg: Config, st: dict, now: float) -> Dict[Tuple[str, str], Optional[List[Show]]]:
    """Fetch every distinct (provider, url) once. None = skipped/failed."""
    plan = {}
    for w in cfg.watches:
        if not w.active:
            continue
        for s in w.sources:
            key = (s.provider, s.url_for(w.date))
            every = s.every_minutes * 60
            prev = plan.get(key)
            # If several watches share a page, use the most frequent schedule.
            plan[key] = (w.date, every if prev is None else min(prev[1], every))

    results = {}
    for (provider, url), (date, every) in plan.items():
        fkey = f"{provider}|{url}"
        last = st["fetch"].get(fkey, 0)
        if every and now - last < every - 30:
            print(f"[{provider}] skipped ({int(now - last)}s since last fetch)")
            results[(provider, url)] = None
            continue
        try:
            results[(provider, url)] = REGISTRY[provider](url, date)
            st["fetch"][fkey] = int(now)
        except Exception as e:  # one broken provider must not stop the rest
            print(f"[{provider}] fetch failed: {e}")
            results[(provider, url)] = None
    return results


def _alert_text(w: Watch, events) -> str:
    links = "\n".join(f"{s.provider}: {s.url_for(w.date)}" for s in w.sources)
    return f"🚨 {w.movie} {w.date}\n\n" + "\n\n".join(e.text for e in events) + "\n\n" + links


def run_once(cfg: Config, state_path: Path, dry_run=False):
    now = time.time()
    st = load_state(state_path, cfg)
    results = fetch_all(cfg, st, now)

    for w in cfg.watches:
        if not w.active:
            continue
        shows = {s.provider: results.get((s.provider, s.url_for(w.date))) for s in w.sources}
        ws = st["watches"].get(w.id, {})
        first_run = not ws.get("initialized")
        events, snapshot, new_ws = evaluate(w, shows, ws)

        print(f"--- watch '{w.id}' ({w.movie} {w.date})")
        print("\n".join(snapshot) or "(no watched theatre is listing the date yet)")
        if dry_run:
            print(f"[dry-run] events: {[e.text.splitlines()[0] for e in events]}")
            continue

        users = [cfg.users[u] for u in w.users]
        if first_run:
            for u in users:
                notify.telegram_message(u, f"👀 Watching {w.movie} on {w.date}.\nAlready listed:\n"
                                           + ("\n".join(snapshot) or "nothing yet"))
        elif events:
            text = _alert_text(w, events)
            for u in users:
                notify.telegram_message(u, text)
            cooldown = w.call_cooldown_minutes * 60
            if now - new_ws["last_call"] >= cooldown or any(e.priority == 0 for e in events):
                spoken = (f"Alert. {w.movie} tickets. {events[0].text.splitlines()[0]}. "
                          "Open Telegram and book now.")
                called = [notify.call(u, spoken) for u in users]
                if any(called):
                    new_ws["last_call"] = int(now)

        st["watches"][w.id] = new_ws

    if not dry_run:
        # drop state for watches removed from config
        live = {w.id for w in cfg.watches}
        st["watches"] = {k: v for k, v in st["watches"].items() if k in live}
        save_state(state_path, st)
