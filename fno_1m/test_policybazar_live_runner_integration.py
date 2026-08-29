import os
from datetime import date


def test_policybazar_runner_module_has_safe_schedule_constants():
    import policybazar_live_runner as m
    assert m.BREAKOUT_CUTOFF.hour == 10
    assert m.TIME_EXIT.hour == 15
    assert m.TIME_EXIT.minute == 5


def test_policybazar_runner_does_not_enable_entries_by_default():
    previous = os.environ.pop("POLICYBAZAR_ENABLE_ENTRIES", None)
    try:
        import importlib
        m = importlib.import_module("policybazar_live_runner")
        assert getattr(m, "ENABLE_ENTRIES", False) is False
    finally:
        if previous is not None:
            os.environ["POLICYBAZAR_ENABLE_ENTRIES"] = previous


def test_policybazar_runner_day_guard():
    from policybazar_live_runner import is_trading_day
    assert is_trading_day(date(2026, 8, 31)) is False
    assert is_trading_day(date(2026, 9, 1)) is True
    assert is_trading_day(date(2026, 9, 4)) is False
