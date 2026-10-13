from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class State(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    TARGET = "TARGET"
    SL = "SL"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


@dataclass
class Setup:
    symbol: str
    token: str
    side: Side
    change_pct: float
    candle_time: str
    open: float
    high: float
    low: float
    close: float
    body_pct: float
    entry: float
    stop: float
    target: float
    state: State = State.PENDING
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None

    @property
    def risk(self) -> float:
        return abs(self.entry - self.stop)

    def process_price(self, price: float) -> Optional[str]:
        """Process one LTP tick. Returns an event name only when state changes."""
        if self.state in {
            State.TARGET,
            State.SL,
            State.INVALIDATED,
            State.EXPIRED,
        }:
            return None

        if self.state == State.PENDING:
            if self.side == Side.LONG:
                # The opposite side must be crossed first to invalidate.
                if price <= self.stop:
                    self.state = State.INVALIDATED
                    return "INVALIDATED"
                if price >= self.entry:
                    self.state = State.ACTIVE
                    self.entry_price = price
                    return "ENTRY"
            else:
                if price >= self.stop:
                    self.state = State.INVALIDATED
                    return "INVALIDATED"
                if price <= self.entry:
                    self.state = State.ACTIVE
                    self.entry_price = price
                    return "ENTRY"
            return None

        if self.state == State.ACTIVE:
            if self.side == Side.LONG:
                # When both levels could be touched in the same market update,
                # we conservatively process SL first for the long position.
                if price <= self.stop:
                    self.state = State.SL
                    self.exit_price = price
                    return "SL"
                if price >= self.target:
                    self.state = State.TARGET
                    self.exit_price = price
                    return "TARGET"
            else:
                if price >= self.stop:
                    self.state = State.SL
                    self.exit_price = price
                    return "SL"
                if price <= self.target:
                    self.state = State.TARGET
                    self.exit_price = price
                    return "TARGET"
        return None


def candle_qualifies(open_: float, high: float, low: float, close: float, min_body_pct: float = 50.0) -> tuple[bool, float]:
    total_range = high - low
    if total_range <= 0:
        return False, 0.0
    body_pct = abs(close - open_) / total_range * 100.0
    return body_pct >= min_body_pct, body_pct


def make_setup(symbol: str, token: str, change_pct: float, candle: list, min_body_pct: float = 50.0, target_r: float = 1.0) -> Optional[Setup]:
    # Angel One candle: [timestamp, open, high, low, close, volume]
    ts, open_, high, low, close, _volume = candle
    qualifies, body_pct = candle_qualifies(open_, high, low, close, min_body_pct)
    if not qualifies:
        return None

    # Use a small tick tolerance. Exact OHLC equality is expected for exchange data.
    if abs(open_ - low) <= 1e-6:
        side = Side.LONG
        entry = high
        stop = low
        target = entry + target_r * (entry - stop)
    elif abs(open_ - high) <= 1e-6:
        side = Side.SHORT
        entry = low
        stop = high
        target = entry - target_r * (stop - entry)
    else:
        return None

    if entry == stop:
        return None

    return Setup(
        symbol=symbol,
        token=token,
        side=side,
        change_pct=change_pct,
        candle_time=str(ts),
        open=float(open_),
        high=float(high),
        low=float(low),
        close=float(close),
        body_pct=body_pct,
        entry=float(entry),
        stop=float(stop),
        target=float(target),
    )
