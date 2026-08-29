from datetime import date

import pytest

from policybazar_options_spec import (
    expiry_week_label,
    is_policybazar_s1_day,
    select_atm_strike,
    select_monthly_expiry,
)


def test_s1_days_are_tue_to_thu_only():
    assert is_policybazar_s1_day(date(2026, 8, 25))
    assert is_policybazar_s1_day(date(2026, 8, 26))
    assert is_policybazar_s1_day(date(2026, 8, 27))
    assert not is_policybazar_s1_day(date(2026, 8, 24))
    assert not is_policybazar_s1_day(date(2026, 8, 28))


def test_monthly_expiry_is_nearest_future_listed_expiry():
    expiries = [date(2026, 8, 27), date(2026, 9, 24), date(2026, 10, 29)]
    assert select_monthly_expiry(expiries, date(2026, 8, 28)) == date(2026, 9, 24)


def test_atm_uses_actual_paired_strikes():
    assert select_atm_strike([1250, 1275, 1300], 1287) == 1300
    assert select_atm_strike([1250, 1275, 1300], 1287) == 1300


def test_expiry_week_label():
    days = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4),
            date(2026, 9, 7), date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10),
            date(2026, 9, 11), date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16),
            date(2026, 9, 17), date(2026, 9, 18), date(2026, 9, 21), date(2026, 9, 22),
            date(2026, 9, 23), date(2026, 9, 24)]
    assert expiry_week_label(date(2026, 9, 1), date(2026, 9, 24), days) == "WEEK_1"
    assert expiry_week_label(date(2026, 9, 21), date(2026, 9, 24), days) == "EXPIRY_WEEK"


def test_no_future_expiry_raises():
    with pytest.raises(ValueError):
        select_monthly_expiry([date(2026, 8, 27)], date(2026, 8, 28))
