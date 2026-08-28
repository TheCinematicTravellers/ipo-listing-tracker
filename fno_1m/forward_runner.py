"""Live F&O 1-minute forward-test runner.

This runner is deliberately safety-first:
- Angel One is market-data only.
- Top 7 gainers/losers are frozen at 09:16 IST.
- The 09:15 candle is evaluated against the existing strategy rules.
- When stock entry is crossed, the nearest-expiry ATM CE/PE is resolved and
  its NFO LTP feed is subscribed dynamically.
- AlgoTest entry is disabled unless FORWARD_TEST_ENABLE_ENTRIES=true.
- AlgoTest exits are NOT guessed or implemented.  Therefore entries should
  remain disabled until the documented exit signal contract is wired.

Run from fno_1m after loading the same Angel environment variables used by
angel_live.py.
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
TIME_EXIT = time(15, 5)

BASE_DIR = os.getenv("NSE_FNO_ORB_DIR", r"C:\Users\megha\nse_fno_orb")
MASTER_FILE = os.getenv("ANGEL_MASTER_FILE", os.path.join(BASE_DIR, "OpenAPIScripMaster.json"))
FNO_LIST_FILE = os.getenv("FNO_STOCK_LIST", os.path.join(BASE_DIR, "fno_stock_list.csv"))

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PIN = os.getenv("ANGEL_PIN")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")
ENABLE_ENTRIES = os.getenv("FORWARD_TEST_ENABLE_ENTRIES", "false").lower() == "true"


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
    return {
        str(row["symbol"]).upper().removesuffix("-EQ"): str(row["token"])
        for row in master
        if str(row.get("exch_seg", "")).upper() == "NSE"
        and str(row.get("symbol", "")).upper().endswith("-EQ")
        and str(row.get("symbol", "")).upper().removesuffix("-EQ") in wanted
        and row.get("token")
    }


def market_quote(api, tokens):
    response = api.getMarketData("FULL", {"NSE": [str(x) for x in tokens]})
    if not isinstance(response, dict) or not response.get("status", True):
        raise RuntimeError(f"Quote failed: {response}")
    return response.get("data", {}).get("fetched", [])


def candle_0915(api, token, day):
    response = api.getCandleData({
        "exchange": "NSE",
        "symboltoken": str(token),
        "interval": "ONE_MINUTE",
        "fromdate": f"{day} 09:15",
        "todate": f"{day} 09:16",
    })
    if not response or not response.get("status", True):
        raise RuntimeError(f"09:15 candle failed for {token}: {response}")
    data = response.get("data") or []
    if not data:
        raise RuntimeError(f"No 09:15 candle for token {token}")
    c = data[0]
    return float(c[1]), float(c[2]), float(c[3]), float(c[4])


@dataclass
class LiveState:
    setup: Setup
    option: dict | None = None
    option_ltp: float | None = None
    entry_sent: bool = False
    invalidated: bool = False
    entered: bool = False
    target: float | None = None


def main():
    now = datetime.now(IST)
    if now.time() < ENTRY_TIME:
        print(f"[WAIT] Start this runner at/after 09:16 IST. Current: {now:%H:%M:%S} IST")
        return
    if now.time() >= TIME_EXIT:
        print("[STOP] After 15:05 IST")
        return

    api, feed_token = login()
    master = load_master()
    symbols = load_symbols()
    token_map = nse_tokens(master, symbols)
    print(f"[OK] Real F&O universe: {len(token_map)}")
    print(f"[OK] Max stock price: Rs {MAX_STOCK_PRICE:.0f}")
    print(f"[OK] AlgoTest entries: {'ENABLED' if ENABLE_ENTRIES else 'DISABLED (safe)'}")

    quotes = []
    all_tokens = list(token_map.values())
    for i in range(0, len(all_tokens), 50):
        quotes.extend(market_quote(api, all_tokens[i:i + 50]))
        time_mod.sleep(0.5)

    rows = []
    for q in quotes:
        try:
            token = str(q["symbolToken"])
            symbol = next((s for s, t in token_map.items() if t == token), None)
            ltp = float(q["ltp"])
            close = float(q["close"])
            if not symbol or DUMMY_MARKER in symbol or ltp <= 0 or ltp > MAX_STOCK_PRICE or close <= 0:
                continue
            rows.append({"symbol": symbol, "token": token, "ltp": ltp, "change_pct": (ltp / close - 1) * 100})
        except (KeyError, TypeError, ValueError):
            continue

    gainers = sorted(rows, key=lambda x: x["change_pct"], reverse=True)[:TOP_N]
    losers = sorted(rows, key=lambda x: x["change_pct"])[:TOP_N]
    ranked = [(x, "LONG") for x in gainers] + [(x, "SHORT") for x in losers]
    print("\n[LOCKED 09:16] Top 7 gainers + Top 7 losers")

    states: dict[str, LiveState] = {}
    option_tokens: dict[str, str] = {}
    token_to_key: dict[str, tuple[str, str]] = {}
    for row, side in ranked:
        try:
            o, h, l, c = candle_0915(api, row["token"], now.date())
            setup = make_setup(row["symbol"], o, h, l, c, side)
            if setup is None:
                print(f"  {row['symbol']:<14} {side:<5} REJECTED 09:15 candle")
                continue
            states[row["symbol"]] = LiveState(setup=setup)
            print(f"  {row['symbol']:<14} {side:<5} READY entry={setup.entry_level:.2f} sl={setup.stock_sl:.2f}")
        except Exception as exc:
            print(f"  {row['symbol']:<14} {side:<5} ERROR {exc}")

    if not states:
        print("[STOP] No qualifying setups among the locked 14")
        return

    sws = SmartWebSocketV2(api.access_token, API_KEY, CLIENT_ID, feed_token)
    token_to_symbol = {row["token"]: row["symbol"] for row, _ in ranked}
    at = AlgoTestForward()

    def subscribe_options(selection, symbol):
        for side_key in ("ce", "pe"):
            leg = selection[side_key]
            option_tokens[str(leg["token"])] = f"{symbol}:{side_key.upper()}"
            token_to_key[str(leg["token"])] = (symbol, side_key.upper())
        sws.subscribe(
            f"options_{symbol}",
            LTP,
            [{"exchangeType": NFO, "tokens": [str(selection["ce"]["token"]), str(selection["pe"]["token"])]}],
        )

    def on_data(wsapp, message):
        try:
            data = json.loads(message) if isinstance(message, str) else message
            token = str(data.get("token", ""))
            raw = data.get("last_traded_price")
            if raw is None:
                return
            ltp = float(raw) / 100.0
            now_ist = datetime.now(IST)
            if now_ist.time() >= TIME_EXIT:
                print("[TIME EXIT] 15:05 IST reached. Runner stopping; no broker exits are sent.")
                try:
                    sws.close_connection()
                except Exception:
                    pass
                return

            if token in option_tokens:
                symbol, _ = token_to_key[token]
                state = states.get(symbol)
                if state and state.entered:
                    state.option_ltp = ltp
                    if state.target and ltp >= state.target:
                        print(f"[TARGET] {symbol} option LTP={ltp:.2f} target={state.target:.2f}")
                return

            symbol = token_to_symbol.get(token)
            if not symbol or symbol not in states:
                return
            state = states[symbol]
            setup = state.setup
            stock_ltp = ltp

            if state.invalidated:
                return
            if not state.entered:
                crossed_invalid = (setup.side == "LONG" and stock_ltp <= setup.stock_sl) or (setup.side == "SHORT" and stock_ltp >= setup.stock_sl)
                crossed_entry = (setup.side == "LONG" and stock_ltp >= setup.entry_level) or (setup.side == "SHORT" and stock_ltp <= setup.entry_level)
                if crossed_invalid and not crossed_entry:
                    state.invalidated = True
                    print(f"[INVALIDATED] {symbol} {setup.side} stock={stock_ltp:.2f}")
                    return
                if crossed_entry:
                    selection = find_atm_contracts(master, symbol, stock_ltp, now_ist.date())
                    state.option = selection
                    subscribe_options(selection, symbol)
                    print(f"[STOCK ENTRY] {symbol} {setup.side} stock={stock_ltp:.2f} -> ATM {selection['strike']} CE/PE")
                    return
            else:
                hit_sl = (setup.side == "LONG" and stock_ltp <= setup.stock_sl) or (setup.side == "SHORT" and stock_ltp >= setup.stock_sl)
                if hit_sl:
                    print(f"[STOCK SL] {symbol} stock={stock_ltp:.2f} | AlgoTest exit intentionally not sent")
        except Exception as exc:
            print(f"[DATA ERROR] {exc}")

    def on_open(wsapp):
        token_values = [row["token"] for row, _ in ranked if row["symbol"] in states]
        for i in range(0, len(token_values), 50):
            sws.subscribe(f"underlying_{i // 50}", LTP, [{"exchangeType": NSE, "tokens": token_values[i:i + 50]}])
        print(f"[OK] WebSocket connected | subscribed {len(token_values)} locked stocks")

    sws.on_data = on_data
    sws.on_open = on_open
    sws.on_error = lambda ws, err: print(f"[WEBSOCKET ERROR] {err}")
    sws.on_close = lambda ws: print("[WEBSOCKET CLOSED]")
    sws.connect()


if __name__ == "__main__":
    main()
