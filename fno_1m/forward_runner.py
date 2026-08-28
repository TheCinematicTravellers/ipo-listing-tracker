"""Live F&O 1-minute forward-test runner.

Safety-first live market-data path:
- Angel One supplies NSE/NFO market data only.
- Top 7 gainers/losers are frozen at 09:16 IST.
- The 09:15 candle is evaluated against the existing strategy rules.
- The option contract is locked from the 09:16 stock LTP and never
  recalculated when the stock later crosses the trigger.
- Forward-test option entries are paper-tracked from the first live option
  LTP after the stock trigger. AlgoTest can additionally receive the entry
  when FORWARD_TEST_ENABLE_ENTRIES=true.
- Exits are tracked locally from option target, stock SL, or 15:30 time exit.
"""
from __future__ import annotations

import csv
import json
import os
import time as time_mod
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pyotp
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

from algotest import AlgoTestForward
from option_feed import find_atm_contracts
from strategy import Setup, make_setup, option_target

IST = ZoneInfo("Asia/Kolkata")
NSE = 1
NFO = 2
LTP = 1
MAX_STOCK_PRICE = 20000.0
TOP_N = 7
DUMMY_MARKER = "NSETEST"
ENTRY_TIME = time(9, 16)
# NSE cash market closes at 15:30 IST. Keep the runner alive through the
# session so a late start can catch up and then continue live monitoring.
TIME_EXIT = time(15, 30)
CANDLE_REQUEST_GAP_SECONDS = 1.1
CANDLE_MIN_INTERVAL_SECONDS = 1.5
RATE_LIMIT_RETRIES = 3
CANDLE_RATE_LIMIT_COOLDOWN_SECONDS = 15.0
_last_candle_request_at = 0.0
OPTION_PRINT_MIN_CHANGE = 0.01

TRADE_LEDGER_FILE = os.path.join(os.path.dirname(__file__), "logs", "option_trade_ledger.csv")
BASE_DIR = os.getenv("NSE_FNO_ORB_DIR", r"C:\Users\megha\nse_fno_orb")
MASTER_FILE = os.getenv("ANGEL_MASTER_FILE", os.path.join(BASE_DIR, "OpenAPIScripMaster.json"))
FNO_LIST_FILE = os.getenv("FNO_STOCK_LIST", os.path.join(BASE_DIR, "fno_stock_list.csv"))
API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PIN = os.getenv("ANGEL_PIN")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")
ENABLE_ENTRIES = os.getenv("FORWARD_TEST_ENABLE_ENTRIES", "false").lower() == "true"


class RateLimitError(RuntimeError):
    @staticmethod
    def is_rate_limit(message: str) -> bool:
        text = str(message).lower()
        return "exceeding access rate" in text or "access denied because of exceeding access rate" in text


def should_print_option_ltp(previous: float | None, current: float) -> bool:
    return previous is None or abs(current - previous) >= OPTION_PRINT_MIN_CHANGE


def lock_option_contract(master, symbol: str, stock_ltp: float, today):
    return find_atm_contracts(master, symbol, stock_ltp, today)


def login():
    if not all([API_KEY, CLIENT_ID, PIN, TOTP_SECRET]):
        raise RuntimeError("Missing Angel credentials")
    api = SmartConnect(api_key=API_KEY)
    session = api.generateSession(CLIENT_ID, PIN, pyotp.TOTP(TOTP_SECRET).now())
    if not session or not session.get("status"):
        raise RuntimeError(f"Angel One login failed: {session}")
    print("[OK] Angel One login successful")
    return api, session["data"]["feedToken"]


def load_master():
    with open(MASTER_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_symbols() -> list[str]:
    with open(FNO_LIST_FILE, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper().removesuffix("-EQ")
        if symbol and DUMMY_MARKER not in symbol:
            out.append(symbol)
    return list(dict.fromkeys(out))


def nse_tokens(master, symbols):
    wanted = set(symbols)
    return {str(row["symbol"]).upper().removesuffix("-EQ"): str(row["token"]) for row in master if str(row.get("exch_seg", "")).upper() == "NSE" and str(row.get("symbol", "")).upper().endswith("-EQ") and str(row.get("symbol", "")).upper().removesuffix("-EQ") in wanted and row.get("token")}


def market_quote(api, tokens):
    response = api.getMarketData("FULL", {"NSE": [str(x) for x in tokens]})
    if not isinstance(response, dict) or not response.get("status", True):
        raise RuntimeError(f"Quote failed: {response}")
    return response.get("data", {}).get("fetched", [])


def _pace_candle_request():
    global _last_candle_request_at
    now = time_mod.monotonic()
    wait = CANDLE_MIN_INTERVAL_SECONDS - (now - _last_candle_request_at)
    if wait > 0:
        time_mod.sleep(wait)
    _last_candle_request_at = time_mod.monotonic()


def historical_candles(api, exchange: str, token: str, day, start_time: str, end_time: str):
    last_error = None
    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        try:
            _pace_candle_request()
            response = api.getCandleData({"exchange": exchange, "symboltoken": str(token), "interval": "ONE_MINUTE", "fromdate": f"{day} {start_time}", "todate": f"{day} {end_time}"})
            if not response or not response.get("status", True):
                message = str(response)
                if RateLimitError.is_rate_limit(message):
                    raise RateLimitError(message)
                raise RuntimeError(f"Historical candles failed for {token}: {response}")
            return response.get("data") or []
        except Exception as exc:
            last_error = exc
            if not RateLimitError.is_rate_limit(str(exc)) or attempt >= RATE_LIMIT_RETRIES:
                raise
            wait = CANDLE_RATE_LIMIT_COOLDOWN_SECONDS * attempt
            print(f"[RATE LIMIT] token={token} retry {attempt}/{RATE_LIMIT_RETRIES} after {wait:.0f}s")
            time_mod.sleep(wait)
    raise RuntimeError(str(last_error))


def _bar_time(bar) -> datetime:
    text = str(bar[0]).replace("Z", "+00:00")
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=IST)
    return value.astimezone(IST)


def candle_0915(api, token, day):
    last_error = None
    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        try:
            _pace_candle_request()
            response = api.getCandleData({"exchange": "NSE", "symboltoken": str(token), "interval": "ONE_MINUTE", "fromdate": f"{day} 09:15", "todate": f"{day} 09:16"})
            if not response or not response.get("status", True):
                message = str(response)
                if RateLimitError.is_rate_limit(message):
                    raise RateLimitError(message)
                raise RuntimeError(f"09:15 candle failed for {token}: {response}")
            data = response.get("data") or []
            if not data:
                raise RuntimeError(f"No 09:15 candle for token {token}")
            c = data[0]
            return float(c[1]), float(c[2]), float(c[3]), float(c[4])
        except Exception as exc:
            last_error = exc
            if not RateLimitError.is_rate_limit(str(exc)) or attempt >= RATE_LIMIT_RETRIES:
                raise
            wait = CANDLE_RATE_LIMIT_COOLDOWN_SECONDS * attempt
            print(f"[RATE LIMIT] token={token} retry {attempt}/{RATE_LIMIT_RETRIES} after {wait:.0f}s")
            time_mod.sleep(wait)
    raise RuntimeError(str(last_error))


# Keep the rest of the existing strategy, state, websocket, ledger and runner
# implementation unchanged below this point.
