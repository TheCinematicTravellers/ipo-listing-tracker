from __future__ import annotations

import argparse
import csv
import json
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


def load_monthly_contracts(master_path: Path, underlying: str) -> dict[date, dict[float, dict[str, dict]]]:
    rows = json.loads(master_path.read_text(encoding="utf-8"))
    name = underlying.upper().removesuffix("-EQ")
    out: dict[date, dict[float, dict[str, dict]]] = {}
    for row in rows:
        if str(row.get("exch_seg", "")).upper() != "NFO":
            continue
        if str(row.get("instrumenttype", "")).upper() not in {"OPTSTK", "OPTIDX"}:
            continue
        if str(row.get("name", "")).upper() != name:
            continue
        expiry = parse_expiry(row.get("expiry"))
        strike = strike_rupees(row)
        symbol = str(row.get("symbol", "")).upper()
        option_type = symbol[-2:]
        if not expiry or not strike or option_type not in {"CE", "PE"} or not row.get("token"):
            continue
        out.setdefault(expiry, {}).setdefault(strike, {})[option_type] = row
    return out


def signal_rows(stock_csv: Path) -> list[dict]:
    df = pd.read_csv(stock_csv)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df["date"] = df["datetime"].dt.date
    df["time"] = df["datetime"].dt.strftime("%H:%M")
    out: list[dict] = []
    for day, sub in df.groupby("date", sort=True):
        if not is_policybazar_s1_day(day):
            continue
        first = sub[sub.time == "09:15"]
        if first.empty:
            continue
        c1 = first.iloc[0]
        rng = float(c1.high) - float(c1.low)
        if rng <= 0:
            continue
        for _, bar in sub[sub.time > "09:15"].iterrows():
            up = float(bar.high) > float(c1.high)
            down = float(bar.low) < float(c1.low)
            if up and down:
                break
            if not (up or down):
                continue
            side = "LONG" if up else "SHORT"
            breakout = float(c1.high) if up else float(c1.low)
            stock_sl = float(c1.low) if up else float(c1.high)
            target = breakout + rng if up else breakout - rng
            if str(bar.time) >= "10:00":
                break
            out.append({
                "date": day.isoformat(),
                "weekday": day.strftime("%A"),
                "stock": "POLICYBZR",
                "side": side,
                "stock_breakout_time": str(bar.time),
                "stock_entry": breakout,
                "stock_sl": stock_sl,
                "stock_target_1r": target,
                "stock_range_1r": rng,
            })
            break
    return out


def build(stock_csv: Path, master_path: Path, output: Path) -> int:
    signals = signal_rows(stock_csv)
    # All stock-option expiries in the Angel master are monthly contracts for stock options.
    master = json.loads(master_path.read_text(encoding="utf-8"))
    grouped: dict[date, dict[float, dict[str, dict]]] = {}
    for row in master:
        if str(row.get("exch_seg", "")).upper() != "NFO":
            continue
        if str(row.get("instrumenttype", "")).upper() != "OPTSTK":
            continue
        if str(row.get("name", "")).upper() != "POLICYBAZAAR":
            continue
        expiry = parse_expiry(row.get("expiry"))
        strike = strike_rupees(row)
        symbol = str(row.get("symbol", "")).upper()
        opt = symbol[-2:]
        if not expiry or strike is None or opt not in {"CE", "PE"} or not row.get("token"):
            continue
        grouped.setdefault(expiry, {}).setdefault(strike, {})[opt] = row

    expiries = sorted(grouped)
    if not expiries:
        raise RuntimeError("No POLICYBAZAAR OPTSTK contracts found in Angel master")

    trading_dates = sorted({date.fromisoformat(x["date"]) for x in signals})
    records=[]
    for sig in signals:
        day=date.fromisoformat(sig["date"])
        future=[e for e in expiries if e >= day]
        if not future:
            continue
        expiry=future[0]
        paired=sorted(k for k,v in grouped[expiry].items() if "CE" in v and "PE" in v)
        if not paired:
            continue
        atm=select_atm_strike(paired, float(sig["stock_entry"]))
        ce=grouped[expiry][atm]["CE"]; pe=grouped[expiry][atm]["PE"]
        records.append({
            **sig,
            "expiry": expiry.isoformat(),
            "expiry_week": expiry_week_label(day, expiry, trading_dates),
            "atm_strike": atm,
            "ce_symbol": ce["symbol"], "ce_token": ce["token"], "ce_lot_size": ce.get("lotsize", ""),
            "pe_symbol": pe["symbol"], "pe_token": pe["token"], "pe_lot_size": pe.get("lotsize", ""),
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(output, index=False)
    return len(records)


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--stock-csv", required=True)
    p.add_argument("--master", required=True)
    p.add_argument("--output", default="data/policybazar_options/manifest.csv")
    args=p.parse_args()
    print(f"[OK] manifest rows={build(Path(args.stock_csv), Path(args.master), Path(args.output))}")
