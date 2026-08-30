from __future__ import annotations

from dataclasses import dataclass
from datetime import time

IST_OPEN = time(9, 15)
SHORT_TRIGGER_TIME = time(9, 20)
SHORT_TRIGGER_END = time(9, 25)
LONG_START_TIME = time(9, 20)
LONG_CUTOFF_TIME = time(10, 0)
TIME_EXIT = time(15, 13)
DEFAULT_QTY = 1000

@dataclass(frozen=True)
class OpeningCandle:
    open: float
    high: float
    low: float
    close: float
    @property
    def range(self) -> float:
        return self.high - self.low

@dataclass
class TradeState:
    side: str
    entry: float
    stop: float
    target: float
    entered: bool = False
    exit_reason: str | None = None
    exit_price: float | None = None

def one_r_target(side: str, entry: float, stop: float) -> float:
    side = side.upper()
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("entry and stop must define positive risk")
    if side == "SHORT": return entry - risk
    if side == "LONG": return entry + risk
    raise ValueError("side must be LONG or SHORT")

def short_signal_allowed(day_weekday: int, event_time: time) -> bool:
    return day_weekday in range(5) and SHORT_TRIGGER_TIME <= event_time < SHORT_TRIGGER_END

def long_signal_allowed(day_weekday: int, event_time: time) -> bool:
    return day_weekday == 1 and LONG_START_TIME <= event_time < LONG_CUTOFF_TIME

def build_short_setup(candle: OpeningCandle) -> TradeState:
    if candle.range <= 0: raise ValueError("09:15 candle has zero range")
    entry, stop = candle.low, candle.high
    return TradeState("SHORT", entry, stop, one_r_target("SHORT", entry, stop))

def build_long_setup(candle: OpeningCandle) -> TradeState:
    if candle.range <= 0: raise ValueError("09:15 candle has zero range")
    entry, stop = candle.high, candle.low
    return TradeState("LONG", entry, stop, one_r_target("LONG", entry, stop))

def exit_reason(side: str, ltp: float, stop: float, target: float, now: time) -> str | None:
    side = side.upper()
    if side == "SHORT":
        if ltp >= stop: return "STOCK_SL"
        if ltp <= target: return "STOCK_1R"
    elif side == "LONG":
        if ltp <= stop: return "STOCK_SL"
        if ltp >= target: return "STOCK_1R"
    else:
        raise ValueError("side must be LONG or SHORT")
    if now >= TIME_EXIT: return "TIME_EXIT_15_13"
    return None
