from dataclasses import dataclass
from typing import Literal

Side = Literal["LONG", "SHORT"]

@dataclass(frozen=True)
class Setup:
    symbol: str
    side: Side
    entry_level: float
    stock_sl: float


def qualifies(open_: float, high: float, low: float, close: float, side: Side, body_min_pct: float = 50.0) -> bool:
    rng = high - low
    if rng <= 0:
        return False
    body_pct = abs(close - open_) / rng * 100.0
    if body_pct < body_min_pct:
        return False
    if side == "LONG":
        return abs(open_ - low) <= max(1e-8, open_ * 1e-6)
    return abs(open_ - high) <= max(1e-8, open_ * 1e-6)


def make_setup(symbol: str, open_: float, high: float, low: float, close: float, side: Side) -> Setup | None:
    if not qualifies(open_, high, low, close, side):
        return None
    if side == "LONG":
        return Setup(symbol, side, high, low)
    return Setup(symbol, side, low, high)


def option_target(entry_ltp: float, target_pct: float = 9.5) -> float:
    return entry_ltp * (1.0 + target_pct / 100.0)


def option_symbol(underlying: str, side: Side, atm_strike: float, expiry: str) -> str:
    # Broker/instrument-token resolution belongs to the market-data adapter.
    suffix = "CE" if side == "LONG" else "PE"
    return f"{underlying}{expiry}{atm_strike:g}{suffix}"
