#!/usr/bin/env python3
"""Backwards-compatible entry point. Prefer: python -m moviealert <command>.

    python watcher.py              == python -m moviealert run
    python watcher.py --loop 60    == python -m moviealert run --loop 60
    python watcher.py --dry-run    == python -m moviealert run --dry-run
    python watcher.py --test-call  == python -m moviealert test-call <first user>
"""
import sys

from moviealert.__main__ import main

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--test-call" in args:
        import json
        from pathlib import Path
        first = next(iter(json.loads((Path(__file__).parent / "watches.json").read_text())["users"]))
        main(["test-call", first])
    else:
        main(["run", *args])
