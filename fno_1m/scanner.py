"""Live orchestration for the F&O 1-minute forward-test strategy.

Angel One provides market data; AlgoTest receives forward-test signals.
There is intentionally no direct broker order placement here.
"""
from dataclasses import dataclass
from datetime import datetime, time
from typing import List

from strategy import Setup, option_target

IST_1505 = time(15, 5)
MAX_STOCK_PRICE = 20000.0
TOP_N = 7
DUMMY_MARKER = "NSETEST"


@dataclass
class Position:
    setup: Setup
    option_symbol: str
    option_entry_ltp: float
    option_target: float
    active: bool = True
    exit_reason: str | None = None

    def check(self, stock_ltp: float, option_ltp: float, now: datetime) -> str | None:
        """Evaluate exits. Stock SL has priority on the same tick."""
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


def _is_real_symbol(row: dict) -> bool:
    symbol = str(row.get("symbol", "")).upper()
    return DUMMY_MARKER not in symbol


def lock_ranked_symbols(
    rows: List[dict],
    max_price: float = MAX_STOCK_PRICE,
    rank_count: int = TOP_N,
) -> dict:
    """Lock Top N gainers/losers at 09:16.

    The strategy universe is the 208 real F&O stocks. Dummy NSETEST symbols are
    rejected defensively, and stocks above the locked maximum price are not
    eligible for ranking/setup selection.
    """
    eligible = []
    for row in rows:
        if not _is_real_symbol(row):
            continue
        try:
            price = float(row["price"])
            change = float(row["change_pct"])
        except (KeyError, TypeError, ValueError):
            continue
        if price <= max_price:
            eligible.append(row)

    gainers = sorted(eligible, key=lambda r: float(r["change_pct"]), reverse=True)[:rank_count]
    losers = sorted(eligible, key=lambda r: float(r["change_pct"]))[:rank_count]
    return {"gainers": gainers, "losers": losers}


def build_position(setup: Setup, option_symbol: str, option_ltp: float) -> Position:
    if option_ltp <= 0:
        raise ValueError("option_ltp must be positive")
    return Position(setup, option_symbol, option_ltp, option_target(option_ltp, 9.5))


def build_0916_snapshot(rows: List[dict]) -> dict:
    """Return the frozen Top-7 snapshot used by the strategy."""
    return lock_ranked_symbols(rows, max_price=MAX_STOCK_PRICE, rank_count=TOP_N)
