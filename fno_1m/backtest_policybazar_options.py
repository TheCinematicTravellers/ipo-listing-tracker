from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from download_policybazar_upstox import cache_path

IST = "Asia/Kolkata"


def localize_ist(values):
    x = pd.to_datetime(values, errors="coerce", utc=True)
    return x.dt.tz_convert(IST)


def load_option(path: Path) -> pd.DataFrame:
    x = pd.read_csv(path)
    if x.empty:
        return x
    x["datetime"] = localize_ist(x["datetime"])
    return x.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)


def first_option_entry(opt: pd.DataFrame, signal_dt: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    x = opt[opt.datetime > signal_dt]
    if x.empty:
        return None
    row = x.iloc[0]
    return row.datetime, float(row.open)


def option_close_at(opt: pd.DataFrame, dt: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    x = opt[opt.datetime <= dt]
    if x.empty:
        return None
    row = x.iloc[-1]
    return row.datetime, float(row.close)


def stock_exit(stock: pd.DataFrame, signal_dt: pd.Timestamp, side: str, entry: float, sl: float, target: float) -> tuple[pd.Timestamp, float, str]:
    bars = stock[stock.datetime >= signal_dt].sort_values("datetime")
    for _, bar in bars.iterrows():
        if side == "LONG":
            hit_target = float(bar.high) >= target
            hit_sl = float(bar.low) <= sl
        else:
            hit_target = float(bar.low) <= target
            hit_sl = float(bar.high) >= sl
        if hit_target and hit_sl:
            # Preserve the frozen stock-side ambiguity treatment: unresolved
            # same-bar collision is not guessed and continues to the next bar.
            continue
        if hit_target:
            return bar.datetime, target, "STOCK_1R"
        if hit_sl:
            return bar.datetime, sl, "STOCK_SL"
    eod = stock[stock.datetime.dt.strftime("%H:%M") == "15:05"]
    eod = eod[eod.datetime >= signal_dt]
    if eod.empty:
        eod = bars
    if eod.empty:
        raise RuntimeError("No stock EOD bar")
    row = eod.iloc[0]
    return row.datetime, float(row.close), "STOCK_15:05"


def option_driven_exit(opt: pd.DataFrame, entry_dt: pd.Timestamp, entry: float, stop_pct: float) -> tuple[pd.Timestamp, float, str]:
    if entry <= 0:
        raise ValueError("Option entry must be positive")
    risk = entry * stop_pct / 100.0
    stop = entry - risk
    target = entry + risk
    bars = opt[opt.datetime >= entry_dt].sort_values("datetime")
    for _, bar in bars.iterrows():
        hit_target = float(bar.high) >= target
        hit_stop = float(bar.low) <= stop
        if hit_target and hit_stop:
            continue
        if hit_target:
            return bar.datetime, target, "OPTION_1R"
        if hit_stop:
            return bar.datetime, stop, "OPTION_SL"
    eod = opt[opt.datetime.dt.strftime("%H:%M") == "15:05"]
    eod = eod[eod.datetime >= entry_dt]
    if eod.empty:
        eod = bars
    if eod.empty:
        raise RuntimeError("No option EOD bar")
    row = eod.iloc[0]
    return row.datetime, float(row.close), "OPTION_15:05"


def run(manifest_path: Path, stock_csv: Path, raw_root: Path, output: Path, option_stop_pct: float) -> int:
    manifest = pd.read_csv(manifest_path)
    stock = pd.read_csv(stock_csv)
    if manifest.empty:
        raise RuntimeError("Manifest is empty")
    stock["datetime"] = localize_ist(stock["datetime"])
    stock = stock.dropna(subset=["datetime"]).sort_values("datetime")
    rows = []

    for _, manifest_row in manifest.iterrows():
        day = pd.Timestamp(manifest_row["date"]).date()
        side = str(manifest_row["side"]).upper()
        signal_dt = pd.Timestamp(f"{manifest_row['date']} {manifest_row['stock_breakout_time']}", tz=IST)
        stock_day = stock[stock.datetime.dt.date == day]
        base = manifest_row.to_dict()
        if stock_day.empty:
            rows.append({**base, "status": "MISSING_STOCK_DATA"})
            continue

        instrument_key = str(manifest_row["option_instrument_key"])
        option_path = cache_path(raw_root, instrument_key)
        if not option_path.exists():
            rows.append({**base, "status": "MISSING_OPTION_DATA"})
            continue
        option = load_option(option_path)
        if option.empty:
            rows.append({**base, "status": "EMPTY_OPTION_DATA"})
            continue

        entry = first_option_entry(option, signal_dt)
        if entry is None:
            rows.append({**base, "status": "MISSING_OPTION_ENTRY"})
            continue
        option_entry_dt, option_entry = entry

        stock_exit_dt, stock_exit_px, stock_exit_reason = stock_exit(
            stock_day,
            signal_dt,
            side,
            float(manifest_row["stock_entry"]),
            float(manifest_row["stock_sl"]),
            float(manifest_row["stock_target_1r"]),
        )
        if stock_exit_dt < option_entry_dt:
            rows.append({
                **base,
                "status": "STOCK_EXIT_BEFORE_OPTION_ENTRY",
                "stock_exit_dt": stock_exit_dt,
                "stock_exit_reason": stock_exit_reason,
                "stock_exit_px": stock_exit_px,
                "option_entry_dt": option_entry_dt,
                "option_entry": option_entry,
            })
            continue

        stock_driven = option_close_at(option, stock_exit_dt)
        if stock_driven is None:
            rows.append({**base, "status": "MISSING_OPTION_STOCK_EXIT"})
            continue
        stock_driven_exit_dt, stock_driven_exit = stock_driven
        lot_size = float(manifest_row.get("option_lot_size", 0) or 0)
        if lot_size <= 0:
            raise RuntimeError(f"Invalid POLICYBZR option lot size for {instrument_key}")

        option_exit_dt, option_exit, option_exit_reason = option_driven_exit(
            option, option_entry_dt, option_entry, option_stop_pct
        )
        rows.append({
            **base,
            "status": "OK",
            "lots": 1,
            "option_entry_dt": option_entry_dt,
            "option_entry": option_entry,
            "option_lot_size": lot_size,
            "stock_exit_dt": stock_exit_dt,
            "stock_exit_reason": stock_exit_reason,
            "stock_exit_px": stock_exit_px,
            "stock_driven_option_exit_dt": stock_driven_exit_dt,
            "stock_driven_option_exit": stock_driven_exit,
            "stock_driven_option_pnl_points": stock_driven_exit - option_entry,
            "stock_driven_option_pnl_rupees": (stock_driven_exit - option_entry) * lot_size,
            "option_exit_dt": option_exit_dt,
            "option_exit_reason": option_exit_reason,
            "option_exit": option_exit,
            "option_driven_option_pnl_points": option_exit - option_entry,
            "option_driven_option_pnl_rupees": (option_exit - option_entry) * lot_size,
            "option_stop_pct": option_stop_pct,
        })

    out = pd.DataFrame(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)
    return len(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/policybazar_options/upstox_manifest.csv")
    parser.add_argument("--stock-csv", required=True)
    parser.add_argument("--raw", default="data/policybazar_options/raw_upstox")
    parser.add_argument("--output", default="data/policybazar_options/trades.csv")
    parser.add_argument("--option-stop-pct", type=float, default=50.0)
    args = parser.parse_args()
    print(f"[OK] option trades={run(Path(args.manifest), Path(args.stock_csv), Path(args.raw), Path(args.output), args.option_stop_pct)}")
