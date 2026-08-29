import pandas as pd

from backtest_policybazar_options import first_option_entry, option_close_at


def test_option_entry_uses_first_candle_strictly_after_signal():
    opt = pd.DataFrame({
        "datetime": pd.to_datetime(["2026-08-12 09:35:00+05:30", "2026-08-12 09:40:00+05:30"]),
        "open": [10, 12], "high": [11, 13], "low": [9, 11], "close": [10.5, 12.5]
    })
    dt, px = first_option_entry(opt, pd.Timestamp("2026-08-12 09:35:00+05:30"))
    assert str(dt) == "2026-08-12 09:40:00+05:30"
    assert px == 12


def test_option_close_at_uses_last_available_candle_before_stock_exit():
    opt = pd.DataFrame({
        "datetime": pd.to_datetime(["2026-08-12 09:40:00+05:30", "2026-08-12 09:45:00+05:30"]),
        "open": [10, 11], "high": [11, 12], "low": [9, 10], "close": [10.5, 11.5]
    })
    dt, px = option_close_at(opt, pd.Timestamp("2026-08-12 09:47:00+05:30"))
    assert str(dt) == "2026-08-12 09:45:00+05:30"
    assert px == 11.5
