from __future__ import annotations

from datetime import date, time


LIVE_ENTRY_START = time(9, 15)
BREAKOUT_CUTOFF = time(10, 0)
TIME_EXIT = time(15, 13)


def is_trading_day(day: date) -> bool:
    return day.weekday() in (1, 2, 3)


def breakout_allowed(when: time) -> bool:
    return LIVE_ENTRY_START <= when < BREAKOUT_CUTOFF


def stock_target_at_1r(side: str, entry: float, stock_sl: float) -> float:
    side = str(side).upper()
    if entry <= 0 or stock_sl <= 0:
        raise ValueError("entry and stock_sl must be positive")
    if side == "LONG":
        return entry + (entry - stock_sl)
    if side == "SHORT":
        return entry - (stock_sl - entry)
    raise ValueError("side must be LONG or SHORT")


def stock_exit_reason(side: str, stock_ltp: float, entry: float, stock_sl: float, target: float) -> str | None:
    side = str(side).upper()
    if side == "LONG":
        if stock_ltp <= stock_sl:
            return "STOCK_SL"
        if stock_ltp >= target:
            return "STOCK_1R"
    elif side == "SHORT":
        if stock_ltp >= stock_sl:
            return "STOCK_SL"
        if stock_ltp <= target:
            return "STOCK_1R"
    else:
        raise ValueError("side must be LONG or SHORT")
    return None


def option_entry_price(live_ltp: float) -> float:
    value = float(live_ltp)
    if value <= 0:
        raise ValueError("live option LTP must be positive")
    return value
