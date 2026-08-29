from __future__ import annotations

import argparse
import json
import calendar
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from policybazar_options_spec import expiry_week_label, is_policybazar_s1_day, select_atm_strike


def parse_expiry(value: object) -> date | None:
    text = str(value or "").strip().upper()
    for fmt in ("%d%b%Y", "%d%b%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def strike_rupees(row: dict) -> float | None:
    try:
        raw = float(row.get("strike"))
    except (TypeError, ValueError):
        return None
    return raw / 100.0 if raw > 0 else None


def load_trading_calendar(calendar_csv: Path | None, fallback_dates: list[date]) -> list[date]:
    if calendar_csv is None:
        return sorted(set(fallback_dates))
    df = pd.read_csv(calendar_csv)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "datetime" not in df.columns:
        raise ValueError("calendar CSV must contain datetime column")
    dt = pd.to_datetime(df["datetime"], errors="coerce").dropna()
    return sorted(set(dt.dt.date.tolist()))


def signal_rows(locked_csv: Path, calendar_csv: Path | None = None) -> tuple[list[dict], list[date]]:
    df = pd.read_csv(locked_csv)
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = {"date", "weekday", "side", "entry_time", "entry", "sl", "target_1r", "risk_per_share", "body_pct"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Locked S1 CSV missing columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["entry_time"] = df["entry_time"].astype(str)
    df["side"] = df["side"].astype(str).str.upper()
    if df["date"].isna().any():
        raise ValueError("Locked S1 CSV contains invalid dates")
    if len(df) != 90:
        raise ValueError(f"Expected authoritative 90-trade POLICYBZR S1 dataset, found {len(df)} rows")
    if not df["body_pct"].astype(float).gt(0.20).all():
        raise ValueError("Locked S1 dataset contains body_pct <= 20% trade")
    if not df["date"].map(is_policybazar_s1_day).all():
        raise ValueError("Locked S1 dataset contains a Monday/Friday/non-Tue-Thu trade")
    if not df["entry_time"].lt("10:00").all():
        raise ValueError("Locked S1 dataset contains entry at/after 10:00")
    if not df["side"].isin({"LONG", "SHORT"}).all():
        raise ValueError("Locked S1 dataset contains invalid side")

    out = []
    for _, row in df.sort_values(["date", "entry_time"]).iterrows():
        out.append({
            "date": row["date"].isoformat(),
            "weekday": str(row["weekday"]),
            "stock": "POLICYBZR",
            "side": row["side"],
            "stock_breakout_time": str(row["entry_time"]),
            "stock_entry": float(row["entry"]),
            "stock_sl": float(row["sl"]),
            "stock_target_1r": float(row["target_1r"]),
            "stock_range_1r": float(row["risk_per_share"]),
            "body_pct": float(row["body_pct"]),
        })
    fallback = sorted(df["date"].tolist())
    return out, load_trading_calendar(calendar_csv, fallback)


def load_contracts(master_path: Path) -> dict[date, dict[float, dict[str, dict]]]:
    master = json.loads(master_path.read_text(encoding="utf-8"))
    grouped: dict[date, dict[float, dict[str, dict]]] = {}
    for row in master:
        if str(row.get("exch_seg", "")).upper() != "NFO":
            continue
        if str(row.get("instrumenttype", "")).upper() != "OPTSTK":
            continue
        if str(row.get("name", "")).upper() != "POLICYBZR":
            continue
        expiry = parse_expiry(row.get("expiry"))
        strike = strike_rupees(row)
        symbol = str(row.get("symbol", "")).upper()
        option_type = symbol[-2:]
        if not expiry or strike is None or option_type not in {"CE", "PE"} or not row.get("token"):
            continue
        grouped.setdefault(expiry, {}).setdefault(strike, {})[option_type] = row
    return grouped


def historical_monthly_expiries(trading_dates: list[date]) -> list[date]:
    """Return the actual historical NSE stock-option monthly expiries.

    NSE kept stock-derivative expiries on Thursday through contracts expiring
    on/before 31-Aug-2025. New contracts expiring on/after 01-Sep-2025 moved
    to the last Tuesday of the month. If that day was a trading holiday, the
    previous trading day was the expiry.
    """
    dates = sorted(set(trading_dates))
    if not dates:
        raise ValueError("Trading calendar is empty")
    months = sorted({(d.year, d.month) for d in dates})
    expiries: list[date] = []
    for year, month in months:
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        # Transition applies to contracts expiring on/after 01-Sep-2025.
        weekday = 3 if last_day <= date(2025, 8, 31) else 1  # Thu=3, Tue=1
        candidates = [d for d in dates if d.year == year and d.month == month and d.weekday() == weekday and d <= last_day]
        if not candidates:
            raise ValueError(f"Could not resolve monthly expiry for {year}-{month:02d}")
        expiries.append(max(candidates))
    return expiries


def build(locked_csv: Path, master_path: Path, output: Path, calendar_csv: Path | None = None) -> int:
    signals, trading_dates = signal_rows(locked_csv, calendar_csv)
    grouped = load_contracts(master_path)
    historical_expiries = historical_monthly_expiries(trading_dates)

    records = []
    missing_master_expiries: dict[str, int] = {}
    for sig in signals:
        day = date.fromisoformat(sig["date"])
        future = [e for e in historical_expiries if e >= day]
        if not future:
            raise RuntimeError(f"No historical monthly expiry on/after signal date {day}")
        expiry = future[0]
        if expiry not in grouped:
            missing_master_expiries[expiry.isoformat()] = missing_master_expiries.get(expiry.isoformat(), 0) + 1
            continue
        paired = sorted(k for k, v in grouped[expiry].items() if "CE" in v and "PE" in v)
        if not paired:
            raise RuntimeError(f"No paired POLICYBZR CE/PE strikes for historical expiry {expiry}")
        atm = select_atm_strike(paired, float(sig["stock_entry"]))
        ce = grouped[expiry][atm]["CE"]
        pe = grouped[expiry][atm]["PE"]
        records.append({
            **sig,
            "expiry": expiry.isoformat(),
            "expiry_week": expiry_week_label(day, expiry, trading_dates),
            "atm_strike": atm,
            "ce_symbol": ce["symbol"], "ce_token": ce["token"], "ce_lot_size": ce.get("lotsize", ""),
            "pe_symbol": pe["symbol"], "pe_token": pe["token"], "pe_lot_size": pe.get("lotsize", ""),
        })

    if missing_master_expiries:
        detail = ", ".join(f"{k} ({v} trades)" for k, v in sorted(missing_master_expiries.items()))
        raise RuntimeError(
            "Historical expiry dates were resolved correctly, but the supplied "
            f"Angel master has no POLICYBZR contracts for: {detail}. "
            "Use a historical contract-master snapshot for those expiry months; "
            "do not substitute the current expiry."
        )
    if len(records) != len(signals):
        raise RuntimeError(f"Contract resolution incomplete: signals={len(signals)} manifest={len(records)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(output, index=False)
    return len(records)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--stock-csv", required=True, help="Authoritative locked 90-trade S1 CSV")
    p.add_argument("--calendar-csv", help="Raw 5m stock CSV used only for the complete trading-date calendar")
    p.add_argument("--master", required=True)
    p.add_argument("--output", default="data/policybazar_options/manifest.csv")
    args = p.parse_args()
    print(f"[OK] manifest rows={build(Path(args.stock_csv), Path(args.master), Path(args.output), Path(args.calendar_csv) if args.calendar_csv else None)}")
