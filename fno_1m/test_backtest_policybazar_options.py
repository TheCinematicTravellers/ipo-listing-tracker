import pandas as pd

from backtest_policybazar_options import first_option_entry, option_close_at, stock_based_option_exit, stock_target_at_r


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


def test_stock_based_option_exit_uses_option_close_at_stock_exit():
    opt = pd.DataFrame({
        "datetime": pd.to_datetime([
            "2026-08-12 09:35:00+05:30",
            "2026-08-12 09:40:00+05:30",
            "2026-08-12 09:45:00+05:30",
        ]),
        "open": [50.0, 52.0, 55.0],
        "high": [51.0, 54.0, 56.0],
        "low": [49.0, 51.0, 54.0],
        "close": [50.5, 53.0, 55.5],
    })

    exit_dt, exit_px, reason = stock_based_option_exit(
        opt,
        pd.Timestamp("2026-08-12 09:35:00+05:30"),
        pd.Timestamp("2026-08-12 09:45:00+05:30"),
    )

    assert exit_dt == pd.Timestamp("2026-08-12 09:45:00+05:30")
    assert exit_px == 55.5
    assert reason == "STOCK_EXIT"


def test_stock_based_option_exit_has_no_premium_target():
    opt = pd.DataFrame({
        "datetime": pd.to_datetime([
            "2026-08-12 09:35:00+05:30",
            "2026-08-12 09:40:00+05:30",
        ]),
        "open": [50.0, 54.0],
        "high": [55.0, 60.0],
        "low": [49.0, 53.0],
        "close": [54.0, 59.0],
    })

    exit_dt, exit_px, reason = stock_based_option_exit(
        opt,
        pd.Timestamp("2026-08-12 09:35:00+05:30"),
        pd.Timestamp("2026-08-12 09:40:00+05:30"),
    )

    assert exit_dt == pd.Timestamp("2026-08-12 09:40:00+05:30")
    assert exit_px == 59.0
    assert reason == "STOCK_EXIT"


def test_stock_target_at_r_scales_original_stock_risk():
    assert stock_target_at_r("LONG", 100.0, 95.0, 0.5) == 102.5
    assert stock_target_at_r("LONG", 100.0, 95.0, 1.0) == 105.0
    assert stock_target_at_r("SHORT", 100.0, 105.0, 0.5) == 97.5
    assert stock_target_at_r("SHORT", 100.0, 105.0, 1.0) == 95.0
