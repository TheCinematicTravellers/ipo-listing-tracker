from __future__ import annotations

from datetime import date
from typing import Iterable
import calendar


def is_policybazar_s1_day(day: date) -> bool:
    return day.weekday() in (1, 2, 3)  # Tue/Wed/Thu


def select_monthly_expiry(expiries: Iterable[date], signal_date: date) -> date:
    candidates = sorted(x for x in expiries if x >= signal_date)
    if not candidates:
        raise ValueError(f"No expiry on/after {signal_date}")
    return candidates[0]


def select_atm_strike(paired_strikes: Iterable[float], stock_price: float) -> float:
    strikes = sorted({float(x) for x in paired_strikes if float(x) > 0})
    if not strikes or stock_price <= 0:
        raise ValueError("Need positive stock price and at least one paired strike")
    return min(strikes, key=lambda strike: (abs(strike - stock_price), strike))


def expiry_week(signal_date: date, expiry_date: date, trading_dates: Iterable[date]) -> int:
    """Return time-to-expiry bucket: 1 farthest, 4 expiry week."""
    dates = sorted({d for d in trading_dates if signal_date <= d <= expiry_date})
    if signal_date not in dates:
        raise ValueError("signal_date must be a trading date")
    if expiry_date not in dates:
        dates.append(expiry_date)
        dates.sort()
    remaining = len(dates)
    if remaining <= 5:
        return 4
    if remaining <= 10:
        return 3
    if remaining <= 15:
        return 2
    return 1


def expiry_week_label(signal_date: date, expiry_date: date, trading_dates: Iterable[date]) -> str:
    week = expiry_week(signal_date, expiry_date, trading_dates)
    return "EXPIRY_WEEK" if week == 4 else f"WEEK_{week}"


def _last_calendar_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def historical_monthly_expiry_candidates(trading_dates: Iterable[date]) -> list[date]:
    """Resolve historical NSE stock-option monthly expiry dates.

    NSE stock derivatives used Thursday expiries for contracts expiring on or
    before 31-Aug-2025 and Tuesday expiries from 01-Sep-2025 onward. For the
    new schedule, a contract expires on the last Tuesday of the month; when
    that Tuesday is a trading holiday, expiry moves to the previous trading day.
    """
    dates = sorted(set(trading_dates))
    if not dates:
        raise ValueError("Trading calendar is empty")

    months = sorted({(d.year, d.month) for d in dates})
    out: list[date] = []
    for year, month in months:
        month_end = _last_calendar_day(year, month)
        if (year, month) == (2025, 8):
            candidates = [d for d in dates if d.year == year and d.month == month and d.weekday() == 3]
            if not candidates:
                raise ValueError("Could not resolve August 2025 expiry")
            out.append(max(candidates))
            continue
        candidates = [
            d for d in dates
            if d.year == year and d.month == month and d.weekday() == 1 and d <= month_end
        ]
        if not candidates:
            raise ValueError(f"Could not resolve historical expiry for {year}-{month:02d}")
        out.append(max(candidates))
    return out


def historical_monthly_expiry_for_signal(signal_date: date, trading_dates: Iterable[date]) -> date:
    return select_monthly_expiry(historical_monthly_expiry_candidates(trading_dates), signal_date)
