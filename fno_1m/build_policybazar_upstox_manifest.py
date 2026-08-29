from __future__ import annotations

import argparse
import json
import os
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import requests

from policybazar_options_spec import expiry_week_label, select_atm_strike

UNDERLYING_KEY = "NSE_EQ|INE417T01026"
BASE_URL = "https://api.upstox.com/v2"
EXPIRY_ENDPOINT = f"{BASE_URL}/expired-instruments/option/contract"


def _load_signals(locked_csv: Path) -> list[dict]:
    df = pd.read_csv(locked_csv)
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = {"date", "weekday", "side", "entry_time", "entry", "sl", "target_1r", "risk_per_share", "body_pct"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Locked S1 CSV missing columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["side"] = df["side"].astype(str).str.upper()
    df["entry_time"] = df["entry_time"].astype(str)
    if df["date"].isna().any():
        raise ValueError("Locked S1 CSV contains invalid dates")
    if len(df) != 90:
        raise ValueError(f"Expected authoritative 90-trade POLICYBZR S1 dataset, found {len(df)} rows")
    if not df["body_pct"].astype(float).gt(0.20).all():
        raise ValueError("Locked S1 dataset contains body_pct <= 20% trade")
    if not df["side"].isin({"LONG", "SHORT"}).all():
        raise ValueError("Locked S1 CSV contains invalid side")
    if not df["entry_time"].lt("10:00").all():
        raise ValueError("Locked S1 CSV contains entry at/after 10:00")

    return [
        {
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
        }
        for _, row in df.sort_values(["date", "entry_time"]).iterrows()
    ]


def _load_trading_calendar(calendar_csv: Path, fallback: Iterable[date]) -> list[date]:
    df = pd.read_csv(calendar_csv)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "datetime" not in df.columns:
        raise ValueError("calendar CSV must contain datetime column")
    dt = pd.to_datetime(df["datetime"], errors="coerce").dropna()
    dates = sorted(set(dt.dt.date.tolist()))
    return dates or sorted(set(fallback))


def last_tuesday(year: int, month: int) -> date:
    day = date(year, month, monthrange(year, month)[1])
    while day.weekday() != 1:
        day -= timedelta(days=1)
    return day


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _candidate_expiry_dates(signal_date: date) -> list[date]:
    year, month = signal_date.year, signal_date.month
    if (year, month) == (2025, 8):
        # Legacy stock-option expiry was Thursday in August 2025.
        candidates = [date(2025, 8, 28), date(2025, 8, 27), date(2025, 8, 26)]
    else:
        candidate = last_tuesday(year, month)
        candidates = [candidate - timedelta(days=i) for i in range(5)]
    if signal_date > candidates[0]:
        year, month = next_month(year, month)
        candidate = last_tuesday(year, month)
        candidates = [candidate - timedelta(days=i) for i in range(5)]
    return [d for d in candidates if d >= signal_date]


def choose_contract_pair(contracts: list[dict], stock_price: float) -> dict:
    pairs: dict[float, dict[str, dict]] = {}
    for contract in contracts:
        try:
            strike = float(contract["strike_price"])
        except (KeyError, TypeError, ValueError):
            continue
        option_type = str(contract.get("instrument_type", "")).upper()
        if strike <= 0 or option_type not in {"CE", "PE"} or not contract.get("instrument_key"):
            continue
        pairs.setdefault(strike, {})[option_type] = contract
    paired = sorted(strike for strike, sides in pairs.items() if {"CE", "PE"}.issubset(sides))
    if not paired:
        raise RuntimeError("No paired POLICYBZR CE/PE strikes returned by Upstox")
    strike = select_atm_strike(paired, stock_price)
    return {"strike": strike, "ce": pairs[strike]["CE"], "pe": pairs[strike]["PE"]}


def fetch_expired_contracts(session: requests.Session, underlying_key: str, expiry_date: date) -> list[dict]:
    response = session.get(
        EXPIRY_ENDPOINT,
        params={"instrument_key": underlying_key, "expiry_date": expiry_date.isoformat()},
        timeout=30,
    )
    if response.status_code != 200:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        raise RuntimeError(f"Upstox expired-contract API failed for {expiry_date}: HTTP {response.status_code}: {payload}")
    payload = response.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Upstox expired-contract API failed for {expiry_date}: {payload}")
    return payload.get("data") or []


def resolve_expiry(signal_date: date, provider: Callable[[date], list[dict]]) -> tuple[date, list[dict]]:
    for candidate in _candidate_expiry_dates(signal_date):
        contracts = provider(candidate)
        if contracts:
            return candidate, contracts
    year, month = next_month(signal_date.year, signal_date.month)
    candidate = last_tuesday(year, month)
    candidates = [candidate - timedelta(days=i) for i in range(5)]
    for candidate in candidates:
        contracts = provider(candidate)
        if contracts:
            return candidate, contracts
    raise RuntimeError(f"No historical POLICYBZR monthly option expiry found on/after {signal_date}")


def resolve_manifest(signals: list[dict], trading_dates: list[date], contract_provider: Callable[[date], list[dict]]) -> list[dict]:
    cache: dict[date, list[dict]] = {}
    rows = []
    for signal in signals:
        signal_date = date.fromisoformat(signal["date"])

        def provider(expiry: date) -> list[dict]:
            if expiry not in cache:
                cache[expiry] = contract_provider(expiry)
            return cache[expiry]

        try:
            expiry, contracts = resolve_expiry(signal_date, provider)
            pair = choose_contract_pair(contracts, float(signal["stock_entry"]))
            selected = pair["ce"] if signal["side"] == "LONG" else pair["pe"]
            rows.append({
                **signal,
                "manifest_status": "OK",
                "expiry": expiry.isoformat(),
                "expiry_week": expiry_week_label(signal_date, expiry),
                "atm_strike": pair["strike"],
                "option_type": selected["instrument_type"],
                "option_instrument_key": selected["instrument_key"],
                "option_symbol": selected.get("trading_symbol", ""),
                "option_exchange_token": selected.get("exchange_token", ""),
                "option_lot_size": selected.get("lot_size", selected.get("minimum_lot", "")),
                "ce_instrument_key": pair["ce"]["instrument_key"],
                "ce_symbol": pair["ce"].get("trading_symbol", ""),
                "pe_instrument_key": pair["pe"]["instrument_key"],
                "pe_symbol": pair["pe"].get("trading_symbol", ""),
            })
        except RuntimeError as exc:
            rows.append({
                **signal,
                "manifest_status": "MISSING_HISTORICAL_CONTRACT",
                "manifest_error": str(exc),
            })
    return rows


def build(locked_csv: Path, calendar_csv: Path, output: Path) -> int:
    signals = _load_signals(locked_csv)
    trading_dates = _load_trading_calendar(calendar_csv, [date.fromisoformat(x["date"]) for x in signals])
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("UPSTOX_ACCESS_TOKEN is not set")

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
    cache_dir = output.parent / "contract_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def provider(expiry: date) -> list[dict]:
        path = cache_dir / f"{expiry.isoformat()}.json"
        if path.exists() and path.stat().st_size > 0:
            print(f"[CACHE] contracts {expiry}")
            return json.loads(path.read_text(encoding="utf-8"))
        print(f"[API] expired contracts {expiry}")
        data = fetch_expired_contracts(session, UNDERLYING_KEY, expiry)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    rows = resolve_manifest(signals, trading_dates, provider)
    if len(rows) != len(signals):
        raise RuntimeError(f"Manifest incomplete: signals={len(signals)} rows={len(rows)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False)
    ok = sum(row.get("manifest_status") == "OK" for row in rows)
    missing = len(rows) - ok
    print(f"[OK] manifest rows={len(rows)} historical_contracts={ok} unavailable={missing}")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-csv", required=True)
    parser.add_argument("--calendar-csv", required=True)
    parser.add_argument("--output", default="data/policybazar_options/upstox_manifest.csv")
    args = parser.parse_args()
    print(f"[DONE] manifest rows={build(Path(args.stock_csv), Path(args.calendar_csv), Path(args.output))}")
