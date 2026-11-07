from __future__ import annotations

from datetime import datetime, timedelta, time


def _market_window() -> tuple[time, time]:
    return time(11, 0), time(17, 0)


def is_market_open(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    start, end = _market_window()
    t = now.time()
    return start <= t <= end


def is_near_market_close(now: datetime | None = None, minutes: int = 20) -> bool:
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    _, end = _market_window()
    close_dt = datetime.combine(now.date(), end)
    delta = close_dt - now
    return timedelta(0) <= delta <= timedelta(minutes=minutes)


def time_to_market_open(now: datetime | None = None) -> timedelta:
    now = now or datetime.now()
    start, _ = _market_window()

    candidate = datetime.combine(now.date(), start)
    if now.weekday() >= 5 or now > candidate:
        days = 1
        while True:
            d = now.date() + timedelta(days=days)
            if d.weekday() < 5:
                candidate = datetime.combine(d, start)
                break
            days += 1

    return max(candidate - now, timedelta(0))
