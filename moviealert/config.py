"""Load and validate watches.json.

Secrets and personal data never live in the file: any string value of the
form "env:NAME" is read from the environment at runtime, so the config can be
committed and shared.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

PROVIDERS = ("district", "bms")


def resolve(value):
    if isinstance(value, str) and value.startswith("env:"):
        return os.environ.get(value[4:]) or None
    return value


@dataclass
class User:
    id: str
    telegram_chat_id: Optional[str] = None
    phone: Optional[str] = None            # E.164, for Twilio calls
    callmebot_user: Optional[str] = None   # "@handle", for free Telegram calls
    calls: bool = True                     # allowed to receive phone calls


@dataclass
class Source:
    provider: str
    url: str                               # may contain {date} / {yyyymmdd}
    every_minutes: int = 0                 # 0 = every run

    def url_for(self, date: str) -> str:
        return self.url.format(date=date, yyyymmdd=date.replace("-", ""))


@dataclass
class TheatreGroup:
    name: str
    match: str                             # regex on cinema name / BMS slug
    format_match: Optional[str] = None     # regex on screen format (District)
    sources: List[str] = field(default_factory=lambda: list(PROVIDERS))
    alert_on_open: bool = True
    alert_on_seats: bool = True


@dataclass
class Watch:
    id: str
    users: List[str]
    movie: str
    date: str                              # YYYY-MM-DD
    sources: List[Source]
    groups: List[TheatreGroup]
    language: Optional[str] = None
    formats: List[str] = field(default_factory=list)   # all must appear in format
    min_seats: int = 1
    show_from: Optional[str] = None        # "HH:MM" inclusive
    show_to: Optional[str] = None          # "HH:MM" inclusive
    call_cooldown_minutes: int = 10
    active: bool = True


@dataclass
class Config:
    users: Dict[str, User]
    watches: List[Watch]


class ConfigError(ValueError):
    pass


def _hhmm(v, where):
    if v is None:
        return None
    if not re.fullmatch(r"\d{2}:\d{2}", str(v)):
        raise ConfigError(f"{where}: expected HH:MM, got {v!r}")
    return v


def load(path) -> Config:
    raw = json.loads(Path(path).read_text())
    errors = []

    users = {}
    for uid, u in (raw.get("users") or {}).items():
        users[uid] = User(
            id=uid,
            telegram_chat_id=resolve(u.get("telegram_chat_id")),
            phone=resolve(u.get("phone")),
            callmebot_user=resolve(u.get("callmebot_user")),
            calls=bool(u.get("calls", True)),
        )

    watches = []
    for i, w in enumerate(raw.get("watches") or []):
        where = f"watches[{i}]"
        try:
            wid = w["id"]
            where = f"watch '{wid}'"
            wusers = w.get("users") or ([w["user"]] if w.get("user") else [])
            for u in wusers:
                if u not in users:
                    errors.append(f"{where}: unknown user '{u}'")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", w["date"]):
                errors.append(f"{where}: date must be YYYY-MM-DD")
            sources = []
            for prov, s in (w.get("sources") or {}).items():
                if prov not in PROVIDERS:
                    errors.append(f"{where}: unknown provider '{prov}'")
                    continue
                sources.append(Source(prov, s["url"], int(s.get("every_minutes", 0))))
            groups = []
            for g in w.get("theatres") or []:
                re.compile(g["match"])
                if g.get("format_match"):
                    re.compile(g["format_match"])
                groups.append(TheatreGroup(
                    name=g["name"], match=g["match"], format_match=g.get("format_match"),
                    sources=g.get("sources") or list(PROVIDERS),
                    alert_on_open=g.get("alert_on_open", True),
                    alert_on_seats=g.get("alert_on_seats", True),
                ))
            if not sources:
                errors.append(f"{where}: needs at least one source")
            if not groups:
                errors.append(f"{where}: needs at least one theatre group")
            watches.append(Watch(
                id=wid, users=wusers, movie=w["movie"], date=w["date"],
                sources=sources, groups=groups,
                language=w.get("language"), formats=w.get("formats") or [],
                min_seats=int(w.get("min_seats", 1)),
                show_from=_hhmm(w.get("show_from"), where),
                show_to=_hhmm(w.get("show_to"), where),
                call_cooldown_minutes=int(w.get("call_cooldown_minutes", 10)),
                active=w.get("active", True),
            ))
        except (KeyError, re.error, ConfigError) as e:
            errors.append(f"{where}: {e}")

    ids = [w.id for w in watches]
    if len(ids) != len(set(ids)):
        errors.append("watch ids must be unique")
    if errors:
        raise ConfigError("invalid config:\n  " + "\n  ".join(errors))
    return Config(users=users, watches=watches)
