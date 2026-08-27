"""Core state model for the 1m F&O forward-test scanner.

Market-data and broker-token adapters are intentionally separated from this module.
No direct Angel One order-placement call exists here.
"""
from dataclasses import dataclass, field
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
        if not self.active:
            return self.exit_reason
        if (self.setup.side == "LONG" and stock_ltp <= self.setup.stock_sl) or (
            self.setup.side == "SHORT" and stock_ltp >= self.setup.stock_sl
        ):
            self.active = False
            self.exit_reason = "STOCK_SL"
        elif option_ltp >= self.option_target:
            self.active = False
            self.exit_reason = "OPTION_TARGET_9.5PCT"
        elif now.time() >= IST_1505:
            self.active = False
            self.exit_reason = "TIME_EXIT_15:05"
        return self.exit_reason


def lock_ranked_symbols(rows: List[dict], max_price: float = 10000.0, rank_count: int = 7) -> dict:
    """Lock Top N gainers/losers at 09:16 using only eligible prices."""
    eligible = [r for r in rows if float(r["price"]) <= max_price]
    gainers = sorted(eligible, key=lambda r: float(r["change_pct"]), reverse=True)[:rank_count]
    losers = sorted(eligible, key=lambda r: float(r["change_pct"]))[:rank_count]
    return {"gainers": gainers, "losers": losers}


def build_position(setup: Setup, option_symbol: str, option_ltp: float) -> Position:
    return Position(setup, option_symbol, option_ltp, option_target(option_ltp, 9.5))
