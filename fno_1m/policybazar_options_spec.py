from __future__ import annotations

from datetime import date
from typing import Iterable


def is_policybazar_s1_day(day: date) -> bool:
    return day.weekday() in (1, 2, 3)  # Tue/Wed/Thu


def select_monthly_expiry(expiries: Iterable[date], signal_date: date) -> date:
    candidates = sorted(x for x in expiries if x >= signal_date)
    if not candidates:
        raise ValueError(f"No expiry on/after {signal_date}")
    # The caller supplies monthly expiries only. Never infer a weekly expiry here.
    return candidates[0]


def select_atm_strike(paired_strikes: Iterable[float], stock_price: float) -> float:
    strikes = sorted({float(x) for x in paired_strikes if float(x) > 0})
    if not strikes or stock_price <= 0:
        raise ValueError("Need positive stock price and at least one paired strike")
    return min(strikes, key=lambda strike: (abs(strike - stock_price), strike))


def expiry_week(signal_date: date, expiry_date: date, trading_dates: Iterable[date]) -> int:
    dates = sorted({d for d in trading_dates if signal_date <= d <= expiry_date})
    if signal_date not in dates:
        raise ValueError("signal_date must be a trading date")
    if expiry_date not in dates:
        dates.append(expiry_date)
        dates.sort()
    return min(4, dates.index(signal_date) // 5 + 1)


def expiry_week_label(signal_date: date, expiry_date: date, trading_dates: Iterable[date]) -> str:
    week = expiry_week(signal_date, expiry_date, trading_dates)
    return "EXPIRY_WEEK" if week >= 4 else f"WEEK_{week}"
