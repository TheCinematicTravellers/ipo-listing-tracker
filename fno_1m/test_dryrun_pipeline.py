from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dryrun_pipeline import IST
from forward_runner import MinuteCandleCollector, algotest_option_symbol, algotest_quantity
from strategy import make_setup, option_target


def test_dryrun_core_path():
    collector = MinuteCandleCollector("09:15")
    base = datetime(2026, 8, 28, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    for j, price in enumerate((100.0, 101.0, 100.0, 101.0)):
        collector.on_ltp("1", price, base + timedelta(seconds=j * 15))
    assert collector.candle("1") == (100.0, 101.0, 100.0, 101.0)

    setup = make_setup("TEST", 100.0, 101.0, 100.0, 101.0, "LONG")
    assert setup is not None
    assert setup.entry_level == 101.0
    assert setup.stock_sl == 100.0
    assert algotest_option_symbol("RELIANCE", "29SEP2026", 1280, "CE") == "RELIANCE260929C1280"
    assert algotest_quantity(500) == 1
    assert option_target(32.80, 9.5) == 35.9
