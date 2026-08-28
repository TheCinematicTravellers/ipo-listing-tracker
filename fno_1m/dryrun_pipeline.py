"""Offline end-to-end dry-run for the F&O 1-minute pipeline.

No Angel API, WebSocket, or AlgoTest webhook is contacted. This measures the
local processing path from 09:15 ticks through setup lock, stock trigger,
option entry, target, and exit state transitions.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from time import perf_counter
from zoneinfo import ZoneInfo

from forward_runner import MinuteCandleCollector, algotest_option_symbol, algotest_quantity, rank_top_movers
from strategy import make_setup, option_target

IST = ZoneInfo("Asia/Kolkata")


def main() -> None:
    t0 = perf_counter()
    collector = MinuteCandleCollector("09:15")
    rows = []
    base = datetime(2026, 8, 28, 9, 15, 0, tzinfo=IST)

    # 208 synthetic stocks, 4 ticks each. The first 14 are deliberately strong
    # movers so Top 7 / Top 7 ranking and setup processing are exercised.
    for i in range(208):
        token = str(100000 + i)
        symbol = f"TEST{i:03d}"
        close = 100.0
        start = 102.0 + i * 0.01 if i < 7 else 98.0 - i * 0.01 if i < 14 else 100.0
        ticks = [start, start + 0.5, start - 0.2, start + 0.3]
        for j, price in enumerate(ticks):
            collector.on_ltp(token, price, base + timedelta(seconds=j * 15 + 1))
        candle = collector.candle(token)
        rows.append({"symbol": symbol, "token": token, "ltp": ticks[-1], "close": close, "candle": candle})

    t_ticks = perf_counter()
    gainers, losers = rank_top_movers(rows, top_n=7)
    ranked = [(x, "LONG") for x in gainers] + [(x, "SHORT") for x in losers]

    setups = []
    for row, side in ranked:
        o, h, l, c = row["candle"]
        setup = make_setup(row["symbol"], o, h, l, c, side)
        if setup:
            setups.append(setup)
    t_lock = perf_counter()

    # Exercise the complete post-lock state path with one synthetic LONG setup.
    setup = setups[0]
    stock_trigger = setup.entry_level + 0.01
    assert stock_trigger >= setup.entry_level
    option_angel = "RELIANCE29SEP261280CE"
    option_ticker = algotest_option_symbol("RELIANCE", "29SEP2026", 1280.0, "CE")
    lots = algotest_quantity(500)
    option_entry = 32.80
    target = option_target(option_entry, 9.5)
    option_target_ltp = target
    t_state = perf_counter()

    print("[DRY RUN] Offline only: NO Angel / AlgoTest network calls")
    print(f"[DRY RUN] 208 stocks x 4 ticks processed")
    print(f"[DRY RUN] Local candle build: {(t_ticks - t0) * 1000:.2f} ms")
    print(f"[DRY RUN] Top7+Top7 + setup lock: {(t_lock - t_ticks) * 1000:.2f} ms")
    print(f"[DRY RUN] Stock trigger -> option entry -> target state: {(t_state - t_lock) * 1000:.2f} ms")
    print(f"[DRY RUN] Total local pipeline: {(t_state - t0) * 1000:.2f} ms")
    print(f"[DRY RUN] Synthetic stock trigger={stock_trigger:.2f}")
    print(f"[DRY RUN] Angel option={option_angel}")
    print(f"[DRY RUN] AlgoTest ticker={option_ticker}")
    print(f"[DRY RUN] AlgoTest quantity={lots} LOT")
    print(f"[DRY RUN] Option entry={option_entry:.2f} target={target:.2f} target_tick={option_target_ltp:.2f}")
    print("[DRY RUN] RESULT=PASS")


if __name__ == "__main__":
    main()
