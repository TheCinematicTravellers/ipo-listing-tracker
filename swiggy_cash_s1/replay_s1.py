from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

from strategy import (
    LONG_CUTOFF_TIME,
    LONG_START_TIME,
    SHORT_TRIGGER_END,
    SHORT_TRIGGER_TIME,
    OpeningCandle,
    build_long_setup,
    build_short_setup,
)


def parse_args():
    p = argparse.ArgumentParser(description="Offline SWIGGY S1 historical replay. Never sends webhooks.")
    p.add_argument("csv", help="5-minute SWIGGY CSV")
    p.add_argument("--dates", nargs="+", help="Optional dates YYYY-MM-DD to replay")
    p.add_argument("--max-trades", type=int, default=10)
    return p.parse_args()


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "datetime" not in df.columns:
        raise ValueError("CSV must contain a datetime column")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").copy()
    df["date"] = df["datetime"].dt.date.astype(str)
    df["time"] = df["datetime"].dt.strftime("%H:%M")
    return df


def replay_day(g: pd.DataFrame):
    c = g[g["time"] == "09:15"]
    if c.empty:
        return None
    c = c.iloc[0]
    opening = OpeningCandle(float(c.open), float(c.high), float(c.low), float(c.close))
    day = c.datetime.dayofweek

    # First directional break after 09:20. For the SHORT setup, only the 09:20 candle is eligible.
    c20 = g[g["time"] == "09:20"]
    if not c20.empty:
        r = c20.iloc[0]
        low_break = float(r.low) < opening.low
        high_break = float(r.high) > opening.high
        if low_break and not high_break:
            setup = build_short_setup(opening)
            return {
                "date": str(c.datetime.date()), "side": "SHORT", "trigger": "09:20 LOW BREAK",
                "entry": setup.entry, "stop": setup.stop, "target": setup.target,
                "entry_ltp": float(r.close) if False else opening.low,
            }

    # Tuesday LONG: first high break from 09:20 to <10:00, unless low breaks first.
    if day == 1:
        window = g[(g["time"] >= "09:20") & (g["time"] < "10:00")]
        for _, r in window.iterrows():
            low_break = float(r.low) < opening.low
            high_break = float(r.high) > opening.high
            if low_break and high_break:
                return {"date": str(c.datetime.date()), "side": "AMBIGUOUS", "trigger": "BOTH SIDES", "entry": "", "stop": "", "target": "", "entry_ltp": ""}
            if low_break:
                return None
            if high_break:
                setup = build_long_setup(opening)
                return {
                    "date": str(c.datetime.date()), "side": "LONG", "trigger": r.datetime.strftime("%H:%M") + " HIGH BREAK",
                    "entry": setup.entry, "stop": setup.stop, "target": setup.target,
                    "entry_ltp": setup.entry,
                }
    return None


def main():
    args = parse_args()
    df = load(args.csv)
    dates = sorted(df["date"].unique())
    if args.dates:
        wanted = set(args.dates)
        dates = [d for d in dates if d in wanted]

    results = []
    for d in dates:
        r = replay_day(df[df["date"] == d])
        if r:
            results.append(r)
        if len(results) >= args.max_trades:
            break

    print("SWIGGY S1 OFFLINE REPLAY")
    print("AlgoTest: DISABLED (this script contains no webhook code)")
    print(f"Input: {args.csv}")
    print(f"Replay dates: {len(dates)}")
    print(f"Signals found: {len(results)}")
    print("-" * 78)
    for r in results:
        print(f"{r['date']} | {r['side']:9} | {r['trigger']:22} | entry={r['entry']} | SL={r['stop']} | 1R={r['target']}")


if __name__ == "__main__":
    main()
