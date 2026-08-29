from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent


def run(cmd:list[str]):
    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, cwd=HERE, check=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stock-csv",required=True,help="Authoritative locked S1 trade CSV")
    p.add_argument("--calendar-csv",required=True,help="Raw 5m stock CSV used for trading calendar/stock exits")
    p.add_argument("--master",required=True)
    p.add_argument("--mode",choices=["manifest","download","backtest","report","all"],default="manifest")
    p.add_argument("--option-stop-pct",type=float,default=50.0)
    a=p.parse_args()
    root=HERE/"data"/"policybazar_options"
    manifest=root/"manifest.csv"
    trades=root/"trades.csv"
    if a.mode in {"manifest","all"}:
        run([sys.executable,"build_policybazar_option_manifest.py","--stock-csv",a.stock_csv,"--calendar-csv",a.calendar_csv,"--master",a.master,"--output",str(manifest)])
    if a.mode in {"download","all"}:
        run([sys.executable,"download_policybazar_options.py","--manifest",str(manifest),"--out",str(root/"raw")])
    if a.mode in {"backtest","all"}:
        run([sys.executable,"backtest_policybazar_options.py","--manifest",str(manifest),"--stock-csv",a.calendar_csv,"--raw",str(root/"raw"),"--output",str(trades),"--option-stop-pct",str(a.option_stop_pct)])
    if a.mode in {"report","all"}:
        run([sys.executable,"report_policybazar_options.py","--trades",str(trades),"--out",str(root)])

if __name__=="__main__":
    main()
