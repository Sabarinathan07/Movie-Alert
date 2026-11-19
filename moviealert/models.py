"""Provider-neutral data shapes."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Show:
    """One showtime (District) or one venue listing (BookMyShow).

    Providers that only expose "this venue is listing the date" (BMS) return
    one Show per venue with detail=False and no time/format/seat fields.
    """

    provider: str
    cinema_id: str
    cinema: str
    sid: Optional[str] = None
    time: Optional[str] = None          # "HH:MM" local
    time_text: str = ""
    fmt: str = ""
    lang: str = ""
    avail: Optional[int] = None
    total: Optional[int] = None
    areas: List[Tuple[str, int, float]] = field(default_factory=list)
    detail: bool = True


@dataclass
class Event:
    priority: int        # 0 = theatre opened, 1 = seats came back
    text: str
