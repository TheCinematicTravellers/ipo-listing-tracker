"""Pure 1-minute setup state machine for the F&O forward scanner.

This module is intentionally isolated from the existing 15-minute mover system.
It contains no broker/order code.
"""
from dataclasses import dataclass
from typing import Literal

Side = Literal["LONG", "SHORT"]
Status = Literal["PENDING", "ACTIVE", "TARGET", "SL", "INVALIDATED"]

EPS = 1e-9


def body_pct(open_: float, high: float, low: float, close: float) -> float:
    rng = high - low
    return 0.0 if rng <= EPS else abs(close - open_) / rng * 100.0


def qualify(open_: float, high: float, low: float, close: float, side: Side, min_body_pct: float = 50.0) -> bool:
    if body_pct(open_, high, low, close) < min_body_pct:
        return False
    if side == "LONG":
        return abs(open_ - low) <= EPS
    return abs(open_ - high) <= EPS


@dataclass
class Setup:
    symbol: str
    side: Side
    open: float
    high: float
    low: float
    close: float
    body_pct: float
    target_r: float
    status: Status = "PENDING"
    entry: float | None = None
    target: float | None = None
    sl: float | None = None
    invalidation_time: str | None = None
    entry_time: str | None = None
    result_time: str | None = None

    def __post_init__(self) -> None:
        self.sl = self.low if self.side == "LONG" else self.high
        self.entry = self.high if self.side == "LONG" else self.low
        risk = abs(self.entry - self.sl)
        self.target = self.entry + risk * self.target_r if self.side == "LONG" else self.entry - risk * self.target_r

    def on_price(self, price: float, timestamp: str) -> Status:
        if self.status == "ACTIVE":
            if self.side == "LONG":
                if price <= self.sl:
                    self.status = "SL"
                elif price >= self.target:
                    self.status = "TARGET"
            else:
                if price >= self.sl:
                    self.status = "SL"
                elif price <= self.target:
                    self.status = "TARGET"
            if self.status in {"TARGET", "SL"}:
                self.result_time = timestamp
            return self.status

        if self.status != "PENDING":
            return self.status

        if self.side == "LONG":
            if price <= self.sl:
                self.status = "INVALIDATED"
                self.invalidation_time = timestamp
            elif price >= self.entry:
                self.status = "ACTIVE"
                self.entry_time = timestamp
        else:
            if price >= self.sl:
                self.status = "INVALIDATED"
                self.invalidation_time = timestamp
            elif price <= self.entry:
                self.status = "ACTIVE"
                self.entry_time = timestamp
        return self.status
