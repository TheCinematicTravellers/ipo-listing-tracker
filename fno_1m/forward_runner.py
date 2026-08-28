"""Live F&O 1-minute forward-test runner.

Safety-first live market-data path:
- Angel One supplies NSE/NFO market data only.
- Top 7 gainers/losers are frozen at 09:16 IST.
- The 09:15 candle is evaluated against the existing strategy rules.
- The option contract is locked from the 09:16 stock LTP and never
  recalculated when the stock later crosses the trigger.
- AlgoTest entry is disabled unless FORWARD_TEST_ENABLE_ENTRIES=true.
- AlgoTest exits remain intentionally disabled because the documented exit
  webhook contract has not been supplied.
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
CANDLE_REQUEST_GAP_SECONDS = 1.1
RATE_LIMIT_RETRIES = 3
OPTION_PRINT_MIN_CHANGE = 0.01

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
    """Print only the first option LTP or a meaningful price change."""
    return previous is None or abs(current - previous) >= OPTION_PRINT_MIN_CHANGE


def lock_option_contract(master, symbol: str, stock_ltp: float, today):
    """Lock the exact Angel option contract from the 09:16 stock LTP."""
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
    last_error = None
    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        try:
            response = api.getCandleData({
                "exchange": "NSE",
                "symboltoken": str(token),
                "interval": "ONE_MINUTE",
                "fromdate": f"{day} 09:15",
                "todate": f"{day} 09:16",
            })
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
            wait = float(2 ** attempt)
            print(f"[RATE LIMIT] token={token} retry {attempt}/{RATE_LIMIT_RETRIES} after {wait:.0f}s")
            time_mod.sleep(wait)
    raise RuntimeError(str(last_error))


@dataclass
class LiveState:
    setup: Setup
    locked_option: dict | None = None
    option_ltp: float | None = None
    entry_sent: bool = False
    invalidated: bool = False
    entered: bool = False
    target: float | None = None
    target_reported: bool = False
    sl_reported: bool = False
    time_exit_reported: bool = False


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
        if i + 50 < len(all_tokens):
            time_mod.sleep(0.5)

    token_to_symbol = {token: symbol for symbol, token in token_map.items()}
    rows = []
    for q in quotes:
        try:
            token = str(q["symbolToken"])
            symbol = token_to_symbol.get(token)
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
    for index, (row, side) in enumerate(ranked):
        if index:
            time_mod.sleep(CANDLE_REQUEST_GAP_SECONDS)
        try:
            o, h, l, c = candle_0915(api, row["token"], now.date())
            setup = make_setup(row["symbol"], o, h, l, c, side)
            if setup is None:
                print(f"  {row['symbol']:<14} {side:<5} REJECTED 09:15 candle")
                continue

            # IMPORTANT: option contract is frozen from the stock LTP at 09:16,
            # not from a later breakout-trigger LTP.
            locked_option = lock_option_contract(master, row["symbol"], row["ltp"], now.date())
            states[row["symbol"]] = LiveState(setup=setup, locked_option=locked_option)
            wanted_side = "CE" if side == "LONG" else "PE"
            contract = locked_option[wanted_side.lower()]
            print(
                f"  {row['symbol']:<14} {side:<5} READY "
                f"stock_ltp_0916={row['ltp']:.2f} "
                f"stock_entry={setup.entry_level:.2f} stock_sl={setup.stock_sl:.2f} "
                f"ATM={locked_option['atm']:.2f} ATM-1={locked_option['strike']:.2f} "
                f"option={contract['symbol']}"
            )
            print(
                f"    STATUS=PENDING | OPTION ENTRY=WAIT | "
                f"TARGET=WAIT | EXIT=WAIT | RESULT=WAIT"
            )
        except Exception as exc:
            print(f"  {row['symbol']:<14} {side:<5} ERROR {exc}")

    if not states:
        print("[STOP] No qualifying setups among the locked 14")
        return

    sws = SmartWebSocketV2(api.access_token, API_KEY, CLIENT_ID, feed_token)
    option_tokens: dict[str, tuple[str, str]] = {}
    at = AlgoTestForward()

    def subscribe_options(selection, symbol):
        tokens = []
        for side_key in ("ce", "pe"):
            leg = selection[side_key]
            option_tokens[str(leg["token"])] = (symbol, side_key.upper())
            tokens.append(str(leg["token"]))
        sws.subscribe(f"options_{symbol}", LTP, [{"exchangeType": NFO, "tokens": tokens}])

    def close_state(symbol: str, state: LiveState, reason: str, exit_ltp: float | None):
        state.entered = False
        state.entry_sent = True
        option = state.locked_option
        side = "CE" if state.setup.side == "LONG" else "PE"
        contract = option[side.lower()] if option else None
        entry = state.option_ltp if state.option_ltp is not None else 0.0
        print(
            f"[RESULT] {symbol} {state.setup.side} | "
            f"OPTION={contract['symbol'] if contract else '-'} | "
            f"ENTRY={entry:.2f} | EXIT={exit_ltp if exit_ltp is not None else 0.0:.2f} | "
            f"RESULT={reason} | STATUS={reason}"
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
                for symbol, state in states.items():
                    if not state.time_exit_reported:
                        state.time_exit_reported = True
                        if state.option_ltp is not None:
                            close_state(symbol, state, "TIME_EXIT_15_05", state.option_ltp)
                        else:
                            print(f"[RESULT] {symbol} {state.setup.side} | STATUS=TIME_EXIT_15_05 | OPTION ENTRY=NOT TRIGGERED")
                try:
                    sws.close_connection()
                except Exception:
                    pass
                return

            if token in option_tokens:
                symbol, option_side = option_tokens[token]
                state = states.get(symbol)
                if not state or not state.locked_option:
                    return
                wanted_side = "CE" if state.setup.side == "LONG" else "PE"
                if option_side != wanted_side:
                    return
                previous = state.option_ltp
                if state.entered and state.target is not None and ltp >= state.target and not state.target_reported:
                    state.option_ltp = ltp
                    state.target_reported = True
                    close_state(symbol, state, "TARGET_9_5PCT", ltp)
                    return
                state.option_ltp = ltp
                contract = state.locked_option[wanted_side.lower()]
                if not should_print_option_ltp(previous, ltp):
                    return
                if not state.entered:
                    print(
                        f"[OPTION QUOTE] {symbol} | OPTION={contract['symbol']} | "
                        f"LTP={ltp:.2f} | LIMIT BUY={ltp:.2f} | STATUS=PENDING"
                    )
                    if not ENABLE_ENTRIES:
                        return
                    at.send_entry(contract["symbol"], state.setup.side, contract["lot_size"])
                    state.entry_sent = True
                    state.entered = True
                    state.target = option_target(ltp, 9.5)
                    print(
                        f"[ACTIVE] {symbol} {state.setup.side} | OPTION={contract['symbol']} | "
                        f"ENTRY={ltp:.2f} | TARGET={state.target:.2f}"
                    )
                return

            symbol = token_to_symbol.get(token)
            if not symbol or symbol not in states:
                return
            state = states[symbol]
            setup = state.setup
            stock_ltp = ltp

            if state.invalidated or state.time_exit_reported:
                return
            if not state.entered:
                crossed_invalid = (setup.side == "LONG" and stock_ltp <= setup.stock_sl) or (setup.side == "SHORT" and stock_ltp >= setup.stock_sl)
                crossed_entry = (setup.side == "LONG" and stock_ltp >= setup.entry_level) or (setup.side == "SHORT" and stock_ltp <= setup.entry_level)
                if crossed_invalid and not crossed_entry:
                    state.invalidated = True
                    print(f"[INVALIDATED] {symbol} {setup.side} | STATUS=INVALIDATED | EXIT=NONE | RESULT=INVALIDATED")
                    return
                if crossed_entry and state.locked_option:
                    wanted_side = "CE" if setup.side == "LONG" else "PE"
                    contract = state.locked_option[wanted_side.lower()]
                    subscribe_options(state.locked_option, symbol)
                    print(
                        f"[STOCK ACTIVE] {symbol} {setup.side} | stock={stock_ltp:.2f} | "
                        f"LOCKED OPTION={contract['symbol']} | ATM={state.locked_option['atm']:.2f} | "
                        f"ATM-1={state.locked_option['strike']:.2f} | STATUS=WAITING_OPTION_ENTRY"
                    )
            else:
                hit_sl = (setup.side == "LONG" and stock_ltp <= setup.stock_sl) or (setup.side == "SHORT" and stock_ltp >= setup.stock_sl)
                if hit_sl and not state.sl_reported:
                    state.sl_reported = True
                    close_state(symbol, state, "STOCK_SL", state.option_ltp)
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
