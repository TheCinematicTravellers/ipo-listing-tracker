"""Live orchestration for the F&O 1-minute forward-test strategy.

The module is designed for local Python execution. Angel One provides market
-data; AlgoTest receives forward-test signals. There is intentionally no
-direct broker order placement here.
"""
from dataclasses import dataclass
from datetime import datetime, time
from typing import Dict, List

from strategy import Setup, option_target

IST_1505 = time(15, 5)


@dataclass
class Position:
    setup: Setup
    option_symbol: str
    option_entry_ltp: float
    option_target: float
    active: bool = True
    exit_reason: str | None = None

    def check(self, stock_ltp: float, option_ltp: float, now: datetime) -> str | None:
        """Evaluate exits. Stock SL has priority over option target on the same tick."""
        if not self.active:
            return self.exit_reason
        stock_sl_hit = (
            (self.setup.side == "LONG" and stock_ltp <= self.setup.stock_sl)
            or (self.setup.side == "SHORT" and stock_ltp >= self.setup.stock_sl)
        )
        if stock_sl_hit:
            self.active = False
            self.exit_reason = "STOCK_SL"
        elif option_ltp >= self.option_target:
            self.active = False
            self.exit_reason = "OPTION_TARGET_9_5PCT"
        elif now.time() >= IST_1505:
            self.active = False
            self.exit_reason = "TIME_EXIT_15_05"
        return self.exit_reason


def lock_ranked_symbols(rows: List[dict], max_price: float = 10000.0, rank_count: int = 7) -> dict:
    """Lock Top N gainers/losers at 09:16 using eligible underlying prices."""
    eligible = [r for r in rows if float(r["price"]) <= max_price]
    gainers = sorted(eligible, key=lambda r: float(r["change_pct"]), reverse=True)[:rank_count]
    losers = sorted(eligible, key=lambda r: float(r["change_pct"]))[:rank_count]
    return {"gainers": gainers, "losers": losers}


def build_position(setup: Setup, option_symbol: str, option_ltp: float) -> Position:
    if option_ltp <= 0:
        raise ValueError("option_ltp must be positive")
    return Position(setup, option_symbol, option_ltp, option_target(option_ltp, 9.5))


def build_0916_snapshot(rows: List[dict]) -> dict:
    """Return the frozen Top-7 snapshot used by the strategy."""
    return lock_ranked_symbols(rows, max_price=10000.0, rank_count=7)
