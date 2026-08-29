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


def stock_based_option_exit(
    opt: pd.DataFrame,
    entry_dt: pd.Timestamp,
    stock_exit_dt: pd.Timestamp,
) -> tuple[pd.Timestamp, float, str]:
    """Exit the option when the underlying stock strategy exits.

    No option-premium target or option-premium stop is applied. The option
    exit is the latest available option close at or before the stock exit.
    """
    x = opt[(opt.datetime >= entry_dt) & (opt.datetime <= stock_exit_dt)]
    if x.empty:
        return stock_exit_dt, float("nan"), "NO_OPTION_PRICE"
    row = x.iloc[-1]
    return row.datetime, float(row.close), "STOCK_EXIT"


def stock_target_at_r(side: str, entry: float, sl: float, target_r: float) -> float:
    """Return the stock target at the requested multiple of original S1 risk."""
    if target_r <= 0:
        raise ValueError("target_r must be positive")
    side = side.upper()
    risk = abs(entry - sl)
    if risk <= 0:
        raise ValueError("Stock entry and stop must define positive risk")
    if side == "LONG":
        return entry + risk * target_r
    if side == "SHORT":
        return entry - risk * target_r
    raise ValueError(f"Unsupported side: {side}")


def stock_exit(stock: pd.DataFrame, signal_dt: pd.Timestamp, side: str, entry: float, sl: float, target: float, target_r: float = 1.0) -> tuple[pd.Timestamp, float, str]:
    bars = stock[stock.datetime >= signal_dt].sort_values("datetime")
    for _, bar in bars.iterrows():
        if side == "LONG":
            hit_target = float(bar.high) >= target
            hit_sl = float(bar.low) <= sl
        else:
            hit_target = float(bar.low) <= target
            hit_sl = float(bar.high) >= sl
        if hit_target and hit_sl:
            continue
        if hit_target:
            return bar.datetime, target, f"STOCK_{target_r:g}R"
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


def target_only_exit(
    opt: pd.DataFrame,
    entry_dt: pd.Timestamp,
    entry: float,
    target_pct: float,
    stock_exit_dt: pd.Timestamp,
) -> tuple[pd.Timestamp, float, str]:
    if entry <= 0:
        raise ValueError("Option entry must be positive")
    target = entry * (1.0 + target_pct / 100.0)
    bars = opt[(opt.datetime >= entry_dt) & (opt.datetime <= stock_exit_dt)].sort_values("datetime")
    for _, bar in bars.iterrows():
        if float(bar.high) >= target:
            return bar.datetime, target, f"OPTION_TARGET_{target_pct:g}PCT"
    stock_close = option_close_at(opt, stock_exit_dt)
    if stock_close is not None:
        return stock_close[0], stock_close[1], "STOCK_EXIT"
    return stock_exit_dt, entry, "NO_OPTION_PRICE"


def run(manifest_path: Path, stock_csv: Path, raw_root: Path, output: Path, target_pct: float | None = None, exit_mode: str = "stock", stock_target_r: float = 1.0) -> int:
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
        if str(manifest_row.get("manifest_status", "OK")) != "OK":
            rows.append({**base, "status": str(manifest_row.get("manifest_status")), "manifest_error": manifest_row.get("manifest_error", "")})
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

        stock_entry = float(manifest_row["stock_entry"])
        stock_sl = float(manifest_row["stock_sl"])
        stock_target = stock_target_at_r(side, stock_entry, stock_sl, stock_target_r)
        stock_exit_dt, stock_exit_px, stock_exit_reason = stock_exit(
            stock_day,
            signal_dt,
            side,
            stock_entry,
            stock_sl,
            stock_target,
            stock_target_r,
        )
        if stock_exit_dt < option_entry_dt:
            rows.append({
                **base,
                "status": "STOCK_EXIT_BEFORE_OPTION_ENTRY",
                "stock_exit_dt": stock_exit_dt,
                "stock_exit_reason": stock_exit_reason,
                "stock_exit_px": stock_exit_px,
                "stock_target_r": stock_target_r,
                "stock_target_px": stock_target,
                "option_entry_dt": option_entry_dt,
                "option_entry": option_entry,
            })
            continue

        lot_size = float(manifest_row.get("option_lot_size", 0) or 0)
        if lot_size <= 0:
            raise RuntimeError(f"Invalid POLICYBZR option lot size for {instrument_key}")

        if exit_mode == "stock":
            exit_dt, exit_px, exit_reason = stock_based_option_exit(
                option, option_entry_dt, stock_exit_dt
            )
        else:
            if target_pct is None:
                raise ValueError("target_pct is required when exit_mode='target'")
            exit_dt, exit_px, exit_reason = target_only_exit(
                option, option_entry_dt, option_entry, target_pct, stock_exit_dt
            )

        pnl = (exit_px - option_entry) * lot_size
        rows.append({
            **base,
            "status": "OK",
            "lots": 1,
            "option_entry_dt": option_entry_dt,
            "option_entry": option_entry,
            "option_lot_size": lot_size,
            "stock_target_r": stock_target_r,
            "stock_target_px": stock_target,
            "stock_exit_dt": stock_exit_dt,
            "stock_exit_reason": stock_exit_reason,
            "stock_exit_px": stock_exit_px,
            "option_target_pct": target_pct if exit_mode == "target" else None,
            "option_exit_mode": exit_mode,
            "option_exit_dt": exit_dt,
            "option_exit_reason": exit_reason,
            "option_exit": exit_px,
            "option_pnl_points": exit_px - option_entry,
            "option_pnl_rupees": pnl,
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
    parser.add_argument("--output", default="data/policybazar_options/trades_target.csv")
    parser.add_argument("--target-pct", type=float, default=None)
    parser.add_argument("--exit-mode", choices=["stock", "target"], default="stock")
    parser.add_argument("--stock-target-r", type=float, default=1.0)
    args = parser.parse_args()
    print(f"[OK] option trades={run(Path(args.manifest), Path(args.stock_csv), Path(args.raw), Path(args.output), args.target_pct, args.exit_mode, args.stock_target_r)}")
