from datetime import datetime
from zoneinfo import ZoneInfo

from forward_runner_1453 import MinuteCandleCollector, should_collect_minute

IST = ZoneInfo("Asia/Kolkata")


def test_local_collector_builds_252_candle_without_api():
    collector = MinuteCandleCollector("252")
    collector.on_ltp("123", 100.0, datetime(2026, 8, 28, 14, 52, 1, tzinfo=IST))
    collector.on_ltp("123", 101.5, datetime(2026, 8, 28, 14, 52, 20, tzinfo=IST))
    collector.on_ltp("123", 99.5, datetime(2026, 8, 28, 14, 52, 40, tzinfo=IST))
    collector.on_ltp("123", 100.8, datetime(2026, 8, 28, 14, 52, 59, tzinfo=IST))

    assert collector.candle("123") == (100.0, 101.5, 99.5, 100.8)


def test_local_collector_ignores_ticks_outside_setup_minute():
    collector = MinuteCandleCollector("252")
    collector.on_ltp("123", 100.0, datetime(2026, 8, 28, 14, 51, 59, tzinfo=IST))
    collector.on_ltp("123", 101.0, datetime(2026, 8, 28, 14, 53, 0, tzinfo=IST))
    assert collector.candle("123") is None


def test_activation_is_after_setup_minute():
    assert should_collect_minute(datetime(2026, 8, 28, 14, 52, 30, tzinfo=IST))
    assert not should_collect_minute(datetime(2026, 8, 28, 14, 53, 0, tzinfo=IST))
