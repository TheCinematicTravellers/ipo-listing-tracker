import json, time
from datetime import datetime
from zoneinfo import ZoneInfo
import yfinance as yf

IST = ZoneInfo("Asia/Kolkata")
OUT = "fno_movers.json"

with open("fno_universe.json", encoding="utf-8") as f:
    symbols = json.load(f)

# Yahoo Finance symbols for NSE equities.
yahoo = {s: f"{s.replace('&','%26').replace('-','-')}.NS" for s in symbols}
rows = []

for start in range(0, len(symbols), 25):
    batch = symbols[start:start+25]
    tickers = [yahoo[s] for s in batch]
    try:
        data = yf.download(
            tickers=tickers,
            period="5d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=True,
        )
    except Exception as e:
        print(f"Batch {start}: {e}")
        continue

    for s in batch:
        t = yahoo[s]
        try:
            x = data[t].dropna(how="all") if hasattr(data, "columns") and t in data.columns.get_level_values(0) else None
            if x is None or len(x) < 2:
                continue
            x = x.tail(2)
            prev = float(x["Close"].iloc[-2])
            row = x.iloc[-1]
            close = float(row["Close"])
            change = (close / prev - 1) * 100 if prev else 0.0
            rows.append({
                "symbol": s,
                "change_pct": round(change, 2),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "cmp": round(close, 2),
                "volume": int(row["Volume"]),
            })
        except Exception as e:
            print(f"{s}: {e}")
    time.sleep(1)

rows.sort(key=lambda x: x["change_pct"], reverse=True)
gainers = rows[:10]
losers = sorted(rows, key=lambda x: x["change_pct"])[:10]
now = datetime.now(IST)

out = {
    "date_ist": now.strftime("%d-%b-%Y"),
    "updated_ist": now.strftime("%d-%b-%Y %I:%M:%S %p"),
    "timezone": "Asia/Kolkata",
    "universe_size": len(symbols),
    "available": len(rows),
    "gainers": gainers,
    "losers": losers,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print(f"Published {len(rows)}/{len(symbols)} stocks at {out['updated_ist']} IST")
