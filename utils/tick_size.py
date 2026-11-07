from __future__ import annotations

import math

from utils.config import get_config


def get_tick_size(price: float) -> float:
    value = float(price)
    if value <= 0:
        return 0.01

    for row in get_config().tick_table:
        min_ok = value >= float(row.min)
        max_ok = row.max is None or value < float(row.max)
        if min_ok and max_ok:
            return float(row.tick)

    return float(get_config().tick_table[-1].tick)


def adjust_price_to_tick(price: float, side: str) -> float:
    value = float(price)
    tick = get_tick_size(value)
    if tick <= 0:
        return value

    ratio = value / tick
    side_lc = str(side).lower()
    if side_lc == "buy":
        adjusted = math.floor(ratio) * tick
    elif side_lc == "sell":
        adjusted = math.ceil(ratio) * tick
    else:
        adjusted = round(ratio) * tick

    return round(adjusted, 8)
