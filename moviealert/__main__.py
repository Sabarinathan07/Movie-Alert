"""CLI.

    python -m moviealert run [--loop SECONDS] [--dry-run]
    python -m moviealert check-config
    python -m moviealert theatres <watch-id>     # list cinemas/formats to configure groups
    python -m moviealert test-call <user-id>
"""

import argparse
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from . import notify
from .config import ConfigError, load
from .providers import REGISTRY
from .runner import run_once

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    ap = argparse.ArgumentParser(prog="moviealert")
    ap.add_argument("--config", default=os.environ.get("WATCH_CONFIG", ROOT / "watches.json"))
    ap.add_argument("--state", default=os.environ.get("WATCH_STATE", ROOT / "watch_state.json"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--loop", type=int, default=0, help="seconds between rounds (0 = once)")
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("check-config")
    t = sub.add_parser("theatres")
    t.add_argument("watch_id")
    c = sub.add_parser("test-call")
    c.add_argument("user_id")
    args = ap.parse_args(argv)

    try:
        cfg = load(args.config)
    except (ConfigError, FileNotFoundError) as e:
        sys.exit(str(e))

    if args.cmd == "check-config":
        print(f"OK: {len(cfg.users)} users, {len(cfg.watches)} watches")
        for w in cfg.watches:
            print(f"  {w.id}: {w.movie} {w.date} -> {', '.join(w.users)} "
                  f"[{', '.join(s.provider for s in w.sources)}] {len(w.groups)} groups")
        return

    if args.cmd == "theatres":
        w = next((w for w in cfg.watches if w.id == args.watch_id), None)
        if not w:
            sys.exit(f"no watch '{args.watch_id}'")
        for s in w.sources:
            shows = REGISTRY[s.provider](s.url_for(w.date), w.date)
            cinemas = defaultdict(list)
            for x in shows:
                cinemas[(x.cinema_id, x.cinema)].append(x)
            print(f"== {s.provider}: {len(cinemas)} cinemas listing {w.date}")
            for (cid, name), xs in sorted(cinemas.items(), key=lambda kv: kv[0][1]):
                fmts = sorted({f"{x.fmt} {x.lang}".strip() for x in xs if x.detail})
                print(f"  {name}  [{cid}]  {'; '.join(fmts)}")
        return

    if args.cmd == "test-call":
        u = cfg.users.get(args.user_id)
        if not u:
            sys.exit(f"no user '{args.user_id}'")
        notify.telegram_message(u, "✅ Test alert from Movie-Alert.")
        notify.call(u, "This is a test call from your movie ticket watcher.")
        return

    while True:
        print(time.strftime("\n== %Y-%m-%d %H:%M:%S =="))
        try:
            run_once(cfg, Path(args.state), dry_run=args.dry_run)
        except Exception as e:
            print(f"[error] {e}")
        if not args.loop:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
