from datetime import datetime, time
from zoneinfo import ZoneInfo

from forward_runner import (
    MinuteCandleCollector,
    algotest_option_symbol,
    algotest_quantity,
    can_start_live_collection,
    rank_top_movers,
)

IST = ZoneInfo("Asia/Kolkata")


def test_local_collector_builds_0915_candle_from_websocket_ticks():
    collector = MinuteCandleCollector("09:15")
    collector.on_ltp("123", 100.0, datetime(2026, 8, 28, 9, 15, 1, tzinfo=IST))
    collector.on_ltp("123", 101.5, datetime(2026, 8, 28, 9, 15, 20, tzinfo=IST))
    collector.on_ltp("123", 99.5, datetime(2026, 8, 28, 9, 15, 40, tzinfo=IST))
    collector.on_ltp("123", 100.8, datetime(2026, 8, 28, 9, 15, 59, tzinfo=IST))
    assert collector.candle("123") == (100.0, 101.5, 99.5, 100.8)


def test_local_collector_ignores_ticks_outside_setup_minute():
    collector = MinuteCandleCollector("09:15")
    collector.on_ltp("123", 100.0, datetime(2026, 8, 28, 9, 14, 59, tzinfo=IST))
    collector.on_ltp("123", 101.0, datetime(2026, 8, 28, 9, 16, 0, tzinfo=IST))
    assert collector.candle("123") is None


def test_rank_top_movers_returns_seven_each_side():
    rows = [
        {"symbol": f"S{i}", "token": str(i), "ltp": 100.0 + i, "close": 100.0}
        for i in range(20)
    ]
    gainers, losers = rank_top_movers(rows, top_n=7)
    assert len(gainers) == 7
    assert len(losers) == 7
    assert gainers[0]["symbol"] == "S19"
    assert losers[0]["symbol"] == "S0"


def test_algotest_uses_one_lot_not_broker_lot_size():
    assert algotest_quantity(500) == 1
    assert algotest_quantity(1250) == 1


def test_algotest_option_symbol_uses_documented_format():
    assert algotest_option_symbol("RELIANCE", "29SEP2026", 1280.0, "CE") == "RELIANCE260929C1280"
    assert algotest_option_symbol("RELIANCE", "29SEP2026", 1280.0, "PE") == "RELIANCE260929P1280"


def test_live_collection_must_start_before_0915():
    assert can_start_live_collection(time(9, 14, 59))
    assert not can_start_live_collection(time(9, 15, 1))
    assert not can_start_live_collection(time(9, 16, 0))
