from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyotp
from SmartApi import SmartConnect

MAX_DAYS = 100
REQUEST_SLEEP = 0.40


def login() -> SmartConnect:
    api_key=os.environ["ANGEL_API_KEY"]
    client_id=os.environ["ANGEL_CLIENT_ID"]
    pin=os.environ["ANGEL_PIN"]
    totp_secret=os.environ["ANGEL_TOTP_SECRET"]
    api=SmartConnect(api_key=api_key)
    session=api.generateSession(client_id, pin, pyotp.TOTP(totp_secret).now())
    if not session or not session.get("status"):
        raise RuntimeError(f"Angel login failed: {session}")
    print("[OK] Angel One login successful")
    return api


def fetch_token(api: SmartConnect, token: str, start: date, end: date) -> pd.DataFrame:
    rows=[]
    cursor=start
    while cursor <= end:
        chunk_end=min(end, cursor + timedelta(days=MAX_DAYS-1))
        params={
            "exchange":"NFO",
            "symboltoken":str(token),
            "interval":"FIVE_MINUTE",
            "fromdate":f"{cursor:%Y-%m-%d} 09:15",
            "todate":f"{chunk_end:%Y-%m-%d} 15:40",
        }
        response=api.getCandleData(params)
        if not response or not response.get("status"):
            raise RuntimeError(f"Historical API failed token={token}: {response}")
        rows.extend(response.get("data") or [])
        print(f"[OK] token={token} {cursor}..{chunk_end} rows={len(response.get('data') or [])}")
        cursor=chunk_end+timedelta(days=1)
        time.sleep(REQUEST_SLEEP)
    if not rows:
        return pd.DataFrame(columns=["datetime","open","high","low","close","volume"])
    out=pd.DataFrame(rows,columns=["datetime","open","high","low","close","volume"])
    out["datetime"]=pd.to_datetime(out["datetime"])
    return out.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",default="data/policybazar_options/manifest.csv")
    p.add_argument("--out",default="data/policybazar_options/raw")
    args=p.parse_args()
    manifest=pd.read_csv(args.manifest)
    if manifest.empty:
        raise RuntimeError("Manifest is empty")
    api=login()
    out_root=Path(args.out)
    for token, group in manifest.groupby("ce_token"):
        dates=pd.to_datetime(group["date"]).dt.date
        path=out_root / str(token) / "candles.csv"
        if path.exists():
            print(f"[CACHE] {path}")
            continue
        data=fetch_token(api,str(token),dates.min(),dates.max())
        path.parent.mkdir(parents=True,exist_ok=True)
        data.to_csv(path,index=False)
    for token, group in manifest.groupby("pe_token"):
        dates=pd.to_datetime(group["date"]).dt.date
        path=out_root / str(token) / "candles.csv"
        if path.exists():
            print(f"[CACHE] {path}")
            continue
        data=fetch_token(api,str(token),dates.min(),dates.max())
        path.parent.mkdir(parents=True,exist_ok=True)
        data.to_csv(path,index=False)
    print("[DONE] option history cache complete")

if __name__ == "__main__":
    main()
