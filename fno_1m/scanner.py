from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pyotp
import requests
from dotenv import load_dotenv
from SmartApi import SmartConnect

from algotest import AlgoTestForward
from strategy import Setup, State, make_setup

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parent.parent
UNIVERSE_FILE = ROOT / "fno_universe.json"
STATUS_FILE = Path(__file__).resolve().parent / "status.json"
SCRIP_MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"

load_dotenv(Path(__file__).resolve().parent / ".env")

BODY_MIN_PCT = float(os.getenv("BODY_MIN_PCT", "50"))
TARGET_R = float(os.getenv("TARGET_R", "1.0"))
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "1.0"))
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")


def now_ist() -> datetime:
    return datetime.now(IST)


def write_status(payload: dict) -> None:
    payload = dict(payload)
    payload["updated_ist"] = now_ist().isoformat()
    STATUS_FILE.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def load_universe() -> list[str]:
    symbols = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
    return [str(s).upper().strip() for s in symbols if str(s).strip()]


def load_scrip_master() -> dict[str, dict]:
    cache = Path(__file__).resolve().parent / "scrip_master_cache.json"
    try:
        if cache.exists() and (time.time() - cache.stat().st_mtime) < 24 * 3600:
            return json.loads(cache.read_text(encoding="utf-8"))
        response = requests.get(SCRIP_MASTER_URL, timeout=30)
        response.raise_for_status()
        raw = response.json()
        selected: dict[str, dict] = {}
        for row in raw:
            if row.get("exch_seg") != "NSE":
                continue
            token = str(row.get("token", ""))
            symbol = str(row.get("symbol", "")).upper()
            name = str(row.get("name", "")).upper()
            if not token:
                continue
            base = symbol[:-3] if symbol.endswith("-EQ") else symbol
            if symbol.endswith("-EQ") or name:
                selected.setdefault(base, {
                    "token": token,
                    "tradingsymbol": symbol,
                    "name": name,
                    "tick_size": row.get("tick_size", "0.05"),
                })
        cache.write_text(json.dumps(selected, indent=2), encoding="utf-8")
        return selected
    except Exception as exc:
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        raise RuntimeError(f"Unable to load Angel One scrip master: {exc}") from exc


def login() -> SmartConnect:
    api_key = os.environ["ANGEL_API_KEY"]
    client = os.environ["ANGEL_CLIENT_CODE"]
    pin = os.environ["ANGEL_PIN"]
    totp_secret = os.environ["ANGEL_TOTP_SECRET"]

    api = SmartConnect(api_key=api_key)
    session = api.generateSession(client, pin, pyotp.TOTP(totp_secret).now())
    if not session.get("status"):
        raise RuntimeError(f"Angel One login failed: {session}")
    return api


def chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def market_quotes(api: SmartConnect, token_rows: list[dict], mode: str = "FULL") -> dict[str, dict]:
    """Fetch at most 50 NSE tokens per call. Calls are deliberately throttled."""
    out: dict[str, dict] = {}
    batches = list(chunks(token_rows, 50))
    for index, batch in enumerate(batches):
        tokens = [str(x["token"]) for x in batch]
        response = api.getMarketData(mode, {"NSE": tokens})
        if not response.get("status"):
            print(f"Market-data batch {index + 1}/{len(batches)} failed: {response}")
        else:
            data = response.get("data") or {}
            fetched = data.get("fetched") if isinstance(data, dict) else None
            if fetched is None and isinstance(data, list):
                fetched = data
            for item in fetched or []:
                token = str(item.get("symbolToken") or item.get("symboltoken") or "")
                if token:
                    out[token] = item
        if index < len(batches) - 1:
            time.sleep(1.05)
    return out


def first_minute_candle(api: SmartConnect, token: str, date_ist: datetime) -> list | None:
    day = date_ist.strftime("%Y-%m-%d")
    response = api.getCandleData({
        "exchange": "NSE",
        "symboltoken": str(token),
        "interval": "ONE_MINUTE",
        "fromdate": f"{day} 09:15",
        "todate": f"{day} 09:16",
    })
    if not response.get("status"):
        print(f"Candle fetch failed for {token}: {response}")
        return None
    candles = response.get("data") or []
    return candles[0] if candles else None


def wait_until_0916() -> None:
    while True:
        now = now_ist()
        if now.weekday() >= 5:
            tomorrow = now + timedelta(days=(7 - now.weekday()))
            target = tomorrow.replace(hour=9, minute=16, second=0, microsecond=0)
        else:
            target = now.replace(hour=9, minute=16, second=0, microsecond=0)
            if now >= target:
                return
        seconds = max(1.0, (target - now).total_seconds())
        print(f"Waiting for 09:16 IST ({int(seconds)}s)")
        time.sleep(min(seconds, 30))


def lock_candidates(api: SmartConnect, universe: list[str], master: dict[str, dict], day: datetime) -> list[Setup]:
    rows = []
    token_rows = []
    for symbol in universe:
        info = master.get(symbol)
        if info:
            token_rows.append({"symbol": symbol, **info})

    quotes = market_quotes(api, token_rows, mode="FULL")
    by_symbol = {str(info["symbol"]): info for info in token_rows}

    for symbol in universe:
        info = by_symbol.get(symbol)
        if not info:
            continue
        q = quotes.get(str(info["token"]))
        if not q:
            continue
        try:
            ltp = float(q.get("ltp"))
            prev_close = float(q.get("close"))
            if prev_close <= 0:
                continue
            change_pct = (ltp / prev_close - 1.0) * 100.0
            rows.append({"symbol": symbol, "token": str(info["token"]), "change_pct": change_pct})
        except (TypeError, ValueError):
            continue

    gainers = sorted(rows, key=lambda x: x["change_pct"], reverse=True)[:10]
    losers = sorted(rows, key=lambda x: x["change_pct"])[:10]
    locked = gainers + losers

    setups: list[Setup] = []
    for row in locked:
        candle = first_minute_candle(api, row["token"], day)
        time.sleep(0.36)
        if candle is None:
            continue
        setup = make_setup(
            row["symbol"],
            row["token"],
            row["change_pct"],
            candle,
            min_body_pct=BODY_MIN_PCT,
            target_r=TARGET_R,
        )
        if setup:
            setups.append(setup)

    write_status({
        "phase": "LOCKED",
        "date_ist": day.strftime("%Y-%m-%d"),
        "universe": len(universe),
        "available_at_0916": len(rows),
        "top10_gainers": gainers,
        "top10_losers": losers,
        "qualified_setups": [setup.__dict__ for setup in setups],
    })
    return setups


def monitor(api: SmartConnect, setups: list[Setup], master: dict[str, dict], day: datetime) -> None:
    token_rows = [{"symbol": s.symbol, "token": s.token, **master[s.symbol]} for s in setups]
    bridge = AlgoTestForward()

    print(f"Monitoring {len(setups)} qualifying 1m setups.")
    while True:
        now = now_ist()
        if now.strftime("%H:%M") >= EXIT_TIME:
            for setup in setups:
                if setup.state in {State.PENDING, State.ACTIVE}:
                    setup.state = State.EXPIRED
            break

        quotes = market_quotes(api, token_rows, mode="LTP") if setups else {}
        events = []
        for setup in setups:
            q = quotes.get(setup.token)
            if not q:
                continue
            try:
                price = float(q.get("ltp"))
            except (TypeError, ValueError):
                continue
            event = setup.process_price(price)
            if event:
                events.append({"symbol": setup.symbol, "event": event, "price": price})
                if event == "ENTRY":
                    # Forward Test only. No Angel One order API is called here.
                    result = bridge.send_entry(setup.symbol, setup.side.value)
                    print(f"ENTRY {setup.symbol} {setup.side.value} @ {price}: {result}")
                else:
                    print(f"{event} {setup.symbol} @ {price}")

        write_status({
            "phase": "MONITORING",
            "date_ist": day.strftime("%Y-%m-%d"),
            "setups": [setup.__dict__ for setup in setups],
            "events": events,
        })
        time.sleep(max(POLL_SECONDS, 1.0))

    write_status({
        "phase": "DONE",
        "date_ist": day.strftime("%Y-%m-%d"),
        "setups": [setup.__dict__ for setup in setups],
    })


def run() -> None:
    print("FNO 1M Top-10 ORB | FORWARD TEST ONLY")
    print(f"Body >= {BODY_MIN_PCT}% | Target = {TARGET_R}R")
    if os.getenv("FORWARD_TEST_ONLY", "true").lower() != "true":
        raise RuntimeError("FORWARD_TEST_ONLY must remain true in this build")

    wait_until_0916()
    day = now_ist()
    universe = load_universe()
    master = load_scrip_master()
    api = login()
    setups = lock_candidates(api, universe, master, day)
    monitor(api, setups, master, day)


if __name__ == "__main__":
    run()
