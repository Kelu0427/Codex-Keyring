from __future__ import annotations

import time
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def now_ms() -> str:
    return str(int(time.time() * 1000))


def format_reset_time(ms: int, include_date: bool) -> str:
    date = datetime.fromtimestamp(ms / 1000)
    return date.strftime("%m-%d %H:%M" if include_date else "%H:%M")
