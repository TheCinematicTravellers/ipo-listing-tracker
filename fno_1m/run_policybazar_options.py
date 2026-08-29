from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(cmd: list[str]) -> None:
    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, cwd=HERE, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-csv", required=True, help="Authoritative locked S1 trade CSV")
    parser.add_argument("--calendar-csv", required=True, help="Raw 5m stock CSV used for trading calendar and stock exits")
    parser.add_argument("--mode", choices=["manifest", "download", "backtest", "report", "all"], default="manifest")
    parser.add_argument("--option-stop-pct", type=float, default=50.0)
    parser.add_argument("--master", help="Legacy Angel master argument; ignored by the Upstox pipeline")
    args = parser.parse_args()

    root = HERE / "data" / "policybazar_options"
    manifest = root / "upstox_manifest.csv"
    trades = root / "trades.csv"
    raw = root / "raw_upstox"

    if args.mode in {"manifest", "all"}:
        run([
            sys.executable,
            "build_policybazar_upstox_manifest.py",
            "--stock-csv", args.stock_csv,
            "--calendar-csv", args.calendar_csv,
            "--output", str(manifest),
        ])
    if args.mode in {"download", "all"}:
        run([
            sys.executable,
            "download_policybazar_upstox.py",
            "--manifest", str(manifest),
            "--out", str(raw),
        ])
    if args.mode in {"backtest", "all"}:
        run([
            sys.executable,
            "backtest_policybazar_options.py",
            "--manifest", str(manifest),
            "--stock-csv", args.calendar_csv,
            "--raw", str(raw),
            "--output", str(trades),
            "--option-stop-pct", str(args.option_stop_pct),
        ])
    if args.mode in {"report", "all"}:
        run([
            sys.executable,
            "report_policybazar_options.py",
            "--trades", str(trades),
            "--out", str(root),
        ])


if __name__ == "__main__":
    main()
