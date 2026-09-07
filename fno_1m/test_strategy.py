from datetime import datetime
from strategy import make_setup, option_target
from scanner import lock_ranked_symbols, build_position


def test_long_open_low_body():
    s = make_setup("ABC", 100, 110, 100, 108, "LONG")
    assert s and s.entry_level == 110 and s.stock_sl == 100


def test_short_open_high_body():
    s = make_setup("ABC", 110, 110, 100, 102, "SHORT")
    assert s and s.entry_level == 100 and s.stock_sl == 110


def test_body_below_50_rejected():
    assert make_setup("ABC", 100, 110, 90, 99, "LONG") is None


def test_target_is_9_5_percent():
    assert option_target(100, 9.5) == 109.5


def test_price_filter_and_top7():
    rows = [{"symbol": str(i), "price": 100, "change_pct": i} for i in range(10)]
    rows.append({"symbol": "EXPENSIVE", "price": 10001, "change_pct": 999})
    locked = lock_ranked_symbols(rows, 10000, 7)
    assert "EXPENSIVE" not in {x["symbol"] for x in locked["gainers"]}
    assert len(locked["gainers"]) == 7


def test_stock_sl_exits_position():
    s = make_setup("ABC", 100, 110, 100, 108, "LONG")
    p = build_position(s, "ABC-CE", 100)
    reason = p.check(100, 101, datetime(2026, 8, 27, 10, 0))
    assert reason == "STOCK_SL"
