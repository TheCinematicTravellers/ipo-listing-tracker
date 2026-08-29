from datetime import date

import pytest

from policybazar_options_spec import (
    expiry_week_label,
    historical_monthly_expiry_for_signal,
    is_policybazar_s1_day,
    select_atm_strike,
    select_monthly_expiry,
)


def weekdays_through_august_2026():
    return [date(2026, 8, d) for d in range(1, 32) if date(2026, 8, d).weekday() < 5]


def test_s1_days_are_tue_to_thu_only():
    assert is_policybazar_s1_day(date(2026, 8, 25))
    assert is_policybazar_s1_day(date(2026, 8, 26))
    assert is_policybazar_s1_day(date(2026, 8, 27))
    assert not is_policybazar_s1_day(date(2026, 8, 24))
    assert not is_policybazar_s1_day(date(2026, 8, 28))


def test_monthly_expiry_is_nearest_future_listed_expiry():
    expiries = [date(2026, 8, 27), date(2026, 9, 24), date(2026, 10, 29)]
    assert select_monthly_expiry(expiries, date(2026, 8, 28)) == date(2026, 9, 24)


def test_august_2026_signal_resolves_last_tuesday():
    assert historical_monthly_expiry_for_signal(date(2026, 8, 12), weekdays_through_august_2026()) == date(2026, 8, 25)


def test_atm_uses_actual_paired_strikes():
    assert select_atm_strike([1250, 1275, 1300], 1287) == 1300


def test_expiry_week_bucket_measures_time_remaining():
    days = [date(2026, 9, d) for d in range(1, 30) if date(2026, 9, d).weekday() < 5]
    assert expiry_week_label(date(2026, 9, 1), date(2026, 9, 29), days) == "WEEK_1"
    assert expiry_week_label(date(2026, 9, 14), date(2026, 9, 29), days) == "WEEK_2"
    assert expiry_week_label(date(2026, 9, 21), date(2026, 9, 29), days) == "WEEK_3"
    assert expiry_week_label(date(2026, 9, 25), date(2026, 9, 29), days) == "EXPIRY_WEEK"


def test_no_future_expiry_raises():
    with pytest.raises(ValueError):
        select_monthly_expiry([date(2026, 8, 27)], date(2026, 8, 28))
