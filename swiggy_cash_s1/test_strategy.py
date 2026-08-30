from datetime import time

from strategy import (
    DEFAULT_QTY,
    LONG_CUTOFF_TIME,
    OpeningCandle,
    build_long_setup,
    build_short_setup,
    exit_reason,
    long_signal_allowed,
    one_r_target,
    short_signal_allowed,
)


def test_default_quantity_is_1000():
    assert DEFAULT_QTY == 1000


def test_short_is_only_the_0920_five_minute_candle():
    assert short_signal_allowed(0, time(9, 20))
    assert short_signal_allowed(4, time(9, 24, 59))
    assert not short_signal_allowed(0, time(9, 19, 59))
    assert not short_signal_allowed(0, time(9, 25))


def test_tuesday_long_is_0920_until_before_10():
    assert long_signal_allowed(1, time(9, 20))
    assert long_signal_allowed(1, time(9, 59, 59))
    assert not long_signal_allowed(1, LONG_CUTOFF_TIME)
    assert not long_signal_allowed(0, time(9, 30))


def test_first_candle_sets_short_entry_sl_and_1r():
    candle = OpeningCandle(200, 202, 196, 198)
    setup = build_short_setup(candle)
    assert setup.side == "SHORT"
    assert setup.entry == 196
    assert setup.stop == 202
    assert setup.target == 190


def test_first_candle_sets_long_entry_sl_and_1r():
    candle = OpeningCandle(200, 202, 196, 201)
    setup = build_long_setup(candle)
    assert setup.side == "LONG"
    assert setup.entry == 202
    assert setup.stop == 196
    assert setup.target == 208


def test_exit_reason_uses_stock_target_and_sl():
    assert exit_reason("SHORT", 202, 202, 190, time(10, 0)) == "STOCK_SL"
    assert exit_reason("SHORT", 190, 202, 190, time(10, 0)) == "STOCK_1R"
    assert exit_reason("LONG", 196, 196, 208, time(10, 0)) == "STOCK_SL"
    assert exit_reason("LONG", 208, 196, 208, time(10, 0)) == "STOCK_1R"


def test_time_exit_is_intraday_safety_close():
    assert exit_reason("LONG", 200, 196, 208, time(15, 13)) == "TIME_EXIT_15_13"


def test_one_r_rejects_zero_risk():
    try:
        one_r_target("LONG", 100, 100)
    except ValueError:
        return
    raise AssertionError("zero-risk setup must be rejected")
