from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

BASE_URL = "https://api.upstox.com/v2"
CANDLE_COLUMNS = ["datetime", "open", "high", "low", "close", "volume", "open_interest"]


def parse_candles(payload: dict) -> pd.DataFrame:
    if payload.get("status") != "success":
        raise RuntimeError(f"Upstox expired-candle API returned failure: {payload}")
    rows = payload.get("data", {}).get("candles") or []
    if not rows:
        return pd.DataFrame(columns=CANDLE_COLUMNS)
    frame = pd.DataFrame(rows, columns=CANDLE_COLUMNS)
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce", utc=True).dt.tz_convert("Asia/Kolkata")
    for col in CANDLE_COLUMNS[1:]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return (
        frame.dropna(subset=["datetime"])
        .drop_duplicates("datetime")
        .sort_values("datetime")
        .reset_index(drop=True)
    )


def safe_key(instrument_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(instrument_key)).strip("_")


def cache_path(root: Path, expired_instrument_key: str) -> Path:
    return root / safe_key(expired_instrument_key) / "candles.csv"


def fetch_expired_candles(
    session: requests.Session,
    expired_instrument_key: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    encoded = quote(expired_instrument_key, safe="")
    url = f"{BASE_URL}/expired-instruments/historical-candle/{encoded}/5minute/{end_date}/{start_date}"
    response = session.get(url, timeout=60)
    if response.status_code != 200:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(
            f"Upstox expired-candle API failed for {expired_instrument_key} {start_date}..{end_date}: "
            f"HTTP {response.status_code}: {detail}"
        )
    return parse_candles(response.json())


def cache_option_candles(manifest: pd.DataFrame, raw_root: Path) -> int:
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("UPSTOX_ACCESS_TOKEN is not set")
    if manifest.empty:
        raise RuntimeError("Manifest is empty")
    required = {"option_instrument_key", "date"}
    missing = required - set(manifest.columns)
    if missing:
        raise ValueError(f"Manifest missing columns: {sorted(missing)}")

    valid = manifest.copy()
    if "manifest_status" in valid.columns:
        valid = valid[valid["manifest_status"].eq("OK")].copy()
    valid = valid[valid["option_instrument_key"].notna()]
    if valid.empty:
        print("[OK] no historical option contracts available to download")
        return 0

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
    raw_root.mkdir(parents=True, exist_ok=True)

    count = 0
    for instrument_key, group in valid.groupby("option_instrument_key", sort=True):
        path = cache_path(raw_root, str(instrument_key))
        if path.exists() and path.stat().st_size > 0:
            print(f"[CACHE] {path}")
            count += 1
            continue
        dates = pd.to_datetime(group["date"], errors="coerce").dropna().dt.date
        if dates.empty:
            raise ValueError(f"No valid signal dates for {instrument_key}")
        start_date = min(dates).isoformat()
        end_date = max(dates).isoformat()
        print(f"[API] candles {instrument_key} {start_date}..{end_date}")
        data = fetch_expired_candles(session, str(instrument_key), start_date, end_date)
        path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(path, index=False)
        print(f"[OK] {instrument_key} rows={len(data)}")
        count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/policybazar_options/upstox_manifest.csv")
    parser.add_argument("--out", default="data/policybazar_options/raw_upstox")
    args = parser.parse_args()
    manifest = pd.read_csv(args.manifest)
    print(f"[OK] cached instruments={cache_option_candles(manifest, Path(args.out))}")
