from datetime import date, time


def test_policybazar_trading_day_is_tuesday_to_thursday_only():
    from policybazar_live_runner import is_trading_day

    assert is_trading_day(date(2026, 9, 1)) is True
    assert is_trading_day(date(2026, 9, 2)) is True
    assert is_trading_day(date(2026, 9, 3)) is True
    assert is_trading_day(date(2026, 8, 31)) is False
    assert is_trading_day(date(2026, 9, 4)) is False


def test_policybazar_breakout_window_starts_after_first_5m_candle():
    from policybazar_live_runner import breakout_allowed

    assert breakout_allowed(time(9, 19, 59)) is False
    assert breakout_allowed(time(9, 20)) is True
    assert breakout_allowed(time(9, 59, 59)) is True
    assert breakout_allowed(time(10, 0)) is False


def test_policybazar_stock_target_is_one_r():
    from policybazar_live_runner import stock_target_at_1r

    assert stock_target_at_1r("LONG", 100.0, 95.0) == 105.0
    assert stock_target_at_1r("SHORT", 100.0, 105.0) == 95.0


def test_policybazar_exit_priority_stock_sl_then_target():
    from policybazar_live_runner import stock_exit_reason

    assert stock_exit_reason("LONG", 94.9, 100.0, 95.0, 105.0) == "STOCK_SL"
    assert stock_exit_reason("LONG", 105.0, 100.0, 95.0, 105.0) == "STOCK_1R"
    assert stock_exit_reason("SHORT", 105.1, 100.0, 105.0, 95.0) == "STOCK_SL"
    assert stock_exit_reason("SHORT", 95.0, 100.0, 105.0, 95.0) == "STOCK_1R"


def test_policybazar_option_entry_is_live_ltp_not_candle_open():
    from policybazar_live_runner import option_entry_price

    assert option_entry_price(42.35) == 42.35


def test_policybazar_entries_default_to_disabled():
    import policybazar_live_runner as m

    assert m.ENABLE_ENTRIES is False
