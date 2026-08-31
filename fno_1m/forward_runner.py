"""Production F&O 1-minute forward runner.

Live-first architecture:
- Start before 09:15 IST; a late start is fail-safe and does not reconstruct
  the 09:15 candle through the historical API.
- Angel One SmartWebSocketV2 QUOTE mode supplies 09:15 ticks plus previous
  close, so the local 09:15 OHLC is built without getCandleData().
- At 09:16:02 IST the Top 7 gainers and Top 7 losers are frozen.
- The 09:15 candle is evaluated with the existing strategy rules.
- The option is locked once from the 09:16 stock LTP and never recalculated.
- A stock trigger is intrabar/live. The first live LTP of the locked option
  after the trigger becomes the option entry.
- AlgoTest receives one lot by default, using its documented ticker format.
- AlgoTest webhook sends are JSON and are deliberately NOT retried, because
  retrying an uncertain order response could duplicate a trade.
- WebSocket reconnect/resubscribe is delegated to SmartWebSocketV2 with a
  bounded retry policy. If the 09:15 candle cannot be collected cleanly,
  the runner stops rather than inventing a setup.
- Local exits are mirrored to AlgoTest with a sell signal for one lot.
"""
from __future__ import annotations

import csv
import json
import os
import threading
import time as time_mod
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
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
QUOTE = 2
MAX_STOCK_PRICE = 20000.0
TOP_N = 7
DUMMY_MARKER = "NSETEST"
SETUP_START = time(9, 15)
FREEZE_TIME = time(9, 16, 2)
TIME_EXIT = time(15, 40)
OPTION_PRINT_MIN_CHANGE = 0.01
ONE_LOT = 1

TRADE_LEDGER_FILE = os.path.join(os.path.dirname(__file__), "logs", "option_trade_ledger.csv")
BASE_DIR = os.getenv("NSE_FNO_ORB_DIR", r"C:\Users\megha\nse_fno_orb")
MASTER_FILE = os.getenv("ANGEL_MASTER_FILE", os.path.join(BASE_DIR, "OpenAPIScripMaster.json"))
FNO_LIST_FILE = os.getenv("FNO_STOCK_LIST", os.path.join(BASE_DIR, "fno_stock_list.csv"))
API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PIN = os.getenv("ANGEL_PIN")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

# Forward-test safety contract:
# - entries are ENABLED by default for this dedicated forward-test branch
# - operator can explicitly disable by setting FORWARD_TEST_ENABLE_ENTRIES=false
ENABLE_ENTRIES = os.getenv("FORWARD_TEST_ENABLE_ENTRIES", "true").lower() == "true"


class RateLimitError(RuntimeError):
    @staticmethod
    def is_rate_limit(message: str) -> bool:
        text = str(message).lower()
        return "exceeding access rate" in text or "access denied because of exceeding access rate" in text


def should_print_option_ltp(previous: float | None, current: float) -> bool:
    return previous is None or abs(current - previous) >= OPTION_PRINT_MIN_CHANGE


def algotest_quantity(lot_size: int | float) -> int:
    """AlgoTest Trade Signals quantity is expressed in lots for this runner."""
    if float(lot_size) <= 0:
        raise ValueError("lot_size must be positive")
    return ONE_LOT


def algotest_option_symbol(underlying: str, expiry: str, strike: float, option_type: str) -> str:
    """Convert Angel's expiry/strike representation to AlgoTest's ticker format."""
    expiry_date = datetime.strptime(str(expiry).upper(), "%d%b%Y")
    cp = str(option_type).upper()
    if cp not in {"CE", "PE"}:
        raise ValueError("option_type must be CE or PE")
    strike_text = f"{float(strike):g}"
    return f"{str(underlying).upper()}{expiry_date:%y%m%d}{'C' if cp == 'CE' else 'P'}{strike_text}"


def can_start_live_collection(now: time) -> bool:
    """Runner must be launched before 09:15 so the whole setup minute is live."""
    return now < SETUP_START


class MinuteCandleCollector:
    def __init__(self, minute: str):
        self.minute = minute
        self._bars: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def on_ltp(self, token: str, ltp: float, when: datetime) -> None:
        if when.astimezone(IST).strftime("%H:%M") != self.minute:
            return
        if ltp <= 0:
            return
        with self._lock:
            self._bars.setdefault(str(token), []).append(float(ltp))

    def candle(self, token: str) -> tuple[float, float, float, float] | None:
        with self._lock:
            values = list(self._bars.get(str(token), []))
        if not values:
            return None
        return values[0], max(values), min(values), values[-1]

    def count(self) -> int:
        with self._lock:
            return len(self._bars)


def _event_time(message: dict[str, Any]) -> datetime:
    raw = message.get("exchange_timestamp")
    if raw is not None:
        try:
            return datetime.fromtimestamp(float(raw) / 1000.0, IST)
        except (TypeError, ValueError, OSError):
            pass
    return datetime.now(IST)


def _ltp(message: dict[str, Any]) -> float | None:
    raw = message.get("last_traded_price")
    if raw is None:
        return None
    try:
        value = float(raw) / 100.0
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def rank_top_movers(rows: list[dict[str, Any]], top_n: int = TOP_N):
    valid = []
    for row in rows:
        try:
            ltp = float(row["ltp"])
            close = float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if ltp <= 0 or close <= 0 or ltp > MAX_STOCK_PRICE:
            continue
        item = dict(row)
        item["ltp"] = ltp
        item["close"] = close
        item["change_pct"] = (ltp / close - 1.0) * 100.0
        valid.append(item)
    gainers = sorted(valid, key=lambda x: x["change_pct"], reverse=True)[:top_n]
    losers = sorted(valid, key=lambda x: x["change_pct"])[:top_n]
    return gainers, losers


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
    return {
        str(row["symbol"]).upper().removesuffix("-EQ"): str(row["token"])
        for row in master
        if str(row.get("exch_seg", "")).upper() == "NSE"
        and str(row.get("symbol", "")).upper().endswith("-EQ")
        and str(row.get("symbol", "")).upper().removesuffix("-EQ") in wanted
        and row.get("token")
    }


def _parse_message(message):
    if isinstance(message, dict):
        return message
    if isinstance(message, str):
        return json.loads(message)
    return None


@dataclass
class LiveState:
    setup: Setup
    locked_option: dict
    option_ltp: float | None = None
    option_entry_ltp: float | None = None
    option_entry_time: str | None = None
    option_exit_ltp: float | None = None
    option_exit_time: str | None = None
    target: float | None = None
    entered: bool = False
    trade_used: bool = False
    entry_sent: bool = False
    exit_sent: bool = False
    invalidated: bool = False
    option_subscribed: bool = False
    target_reported: bool = False
    sl_reported: bool = False
    time_exit_reported: bool = False
    exit_reason: str | None = None
    ledger_written: bool = False


def ensure_ledger_file():
    os.makedirs(os.path.dirname(TRADE_LEDGER_FILE), exist_ok=True)
    if os.path.exists(TRADE_LEDGER_FILE):
        return
    with open(TRADE_LEDGER_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            "date", "stock", "direction", "option", "option_entry_time",
            "option_entry", "stock_sl", "target", "option_exit_time",
            "option_exit", "exit_reason", "result", "pnl", "pnl_pct",
        ])


def write_trade_ledger(symbol: str, state: LiveState):
    if state.ledger_written or state.option_entry_ltp is None or state.option_exit_ltp is None:
        return
    side = "CE" if state.setup.side == "LONG" else "PE"
    contract = state.locked_option[side.lower()]
    entry = state.option_entry_ltp
    exit_ltp = state.option_exit_ltp
    pnl = exit_ltp - entry
    result = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT"
    with open(TRADE_LEDGER_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            state.option_entry_time[:10] if state.option_entry_time else "",
            symbol, state.setup.side, contract["symbol"], state.option_entry_time or "",
            f"{entry:.2f}", f"{state.setup.stock_sl:.2f}", f"{state.target:.2f}",
            state.option_exit_time or "", f"{exit_ltp:.2f}", state.exit_reason or "",
            result, f"{pnl:.2f}", f"{(pnl / entry * 100.0):.2f}",
        ])
    state.ledger_written = True


def main():
    ensure_ledger_file()
    now = datetime.now(IST)
    if now.time() >= TIME_EXIT:
        print("[STOP] After 15:40 IST")
        return
    if not can_start_live_collection(now.time()):
        print("[SAFE STOP] Runner must be started before 09:15 IST; no historical 09:15 reconstruction is used.")
        return

    api, feed_token = login()
    master = load_master()
    symbols = load_symbols()
    token_map = nse_tokens(master, symbols)
    if len(token_map) < 200:
        raise RuntimeError(f"F&O universe incomplete: {len(token_map)} stocks")
    print(f"[OK] Real F&O universe: {len(token_map)}")
    print(f"[OK] Max stock price: Rs {MAX_STOCK_PRICE:.0f}")
    print(f"[OK] AlgoTest entries: {'ENABLED' if ENABLE_ENTRIES else 'DISABLED (paper forward-test)'}")
    print("[ARCH] 09:15 candle source = LIVE WEBSOCKET QUOTE | Historical candle API = DISABLED")
    print("[ARCH] AlgoTest quantity = 1 LOT | Webhook retries = DISABLED to prevent duplicate orders")

    token_to_symbol = {token: symbol for symbol, token in token_map.items()}
    collector = MinuteCandleCollector("09:15")
    latest_quotes: dict[str, dict[str, float]] = {}
    states: dict[str, LiveState] = {}
    option_tokens: dict[str, tuple[str, str]] = {}
    ws_ready = threading.Event()
    freeze_done = threading.Event()

    sws = SmartWebSocketV2(
        api.access_token,
        API_KEY,
        CLIENT_ID,
        feed_token,
        max_retry_attempt=5,
        retry_strategy=1,
        retry_delay=2,
        retry_multiplier=2,
        retry_duration=5,
    )

    def subscribe_stock_quotes():
        tokens = list(token_map.values())
        for i in range(0, len(tokens), 50):
            sws.subscribe(
                f"stocks_{i // 50}",
                QUOTE,
                [{"exchangeType": NSE, "tokens": tokens[i:i + 50]}],
            )
        print(f"[LIVE FEED] Subscribed {len(tokens)} NSE stocks | QUOTE mode")

    def subscribe_options(symbol: str):
        state = states[symbol]
        if state.option_subscribed:
            return
        wanted = "ce" if state.setup.side == "LONG" else "pe"
        legs = [state.locked_option["ce"], state.locked_option["pe"]]
        for leg in legs:
            option_tokens[str(leg["token"])] = (symbol, "CE" if leg is state.locked_option["ce"] else "PE")
        sws.subscribe(
            f"option_{symbol}",
            LTP,
            [{"exchangeType": NFO, "tokens": [str(x["token"]) for x in legs]}],
        )
        state.option_subscribed = True
        contract = state.locked_option[wanted]
        print(f"[OPTION FEED] {symbol} {state.setup.side} subscribed {contract['symbol']}")

    def send_entry(symbol: str, state: LiveState, ltp: float):
        if state.trade_used or state.exit_sent or state.invalidated:
            return
        side_key = "ce" if state.setup.side == "LONG" else "pe"
        contract = state.locked_option[side_key]
        state.option_entry_ltp = ltp
        state.option_entry_time = datetime.now(IST).isoformat(timespec="seconds")
        state.target = option_target(ltp, 9.5)
        state.entry_sent = True
        state.entered = True
        state.trade_used = True
        print(
            f"[OPTION ENTRY] {symbol} {state.setup.side} | OPTION={contract['symbol']} | "
            f"ENTRY={ltp:.2f} | TARGET={state.target:.2f} | LOTS=1"
        )
        if ENABLE_ENTRIES:
            ticker = algotest_option_symbol(
                symbol, state.locked_option["expiry"], contract["strike"], side_key.upper()
            )
            result = AlgoTestForward().send_entry(ticker, "LONG", algotest_quantity(contract["lot_size"]))
            print(f"[ALGOTEST] ENTRY SENT {ticker} | LOTS=1 | HTTP={result['status_code']}")
        else:
            print("[ALGOTEST] ENTRY SKIPPED | FORWARD_TEST_ENABLE_ENTRIES=false")

    def send_exit(symbol: str, state: LiveState, reason: str, exit_ltp: float | None):
        if not state.entered or state.exit_sent:
            return
        side_key = "ce" if state.setup.side == "LONG" else "pe"
        contract = state.locked_option[side_key]
        state.option_exit_ltp = exit_ltp if exit_ltp is not None else state.option_ltp
        state.option_exit_time = datetime.now(IST).isoformat(timespec="seconds")
        state.exit_reason = reason
        if ENABLE_ENTRIES:
            ticker = algotest_option_symbol(
                symbol, state.locked_option["expiry"], contract["strike"], side_key.upper()
            )
            result = AlgoTestForward().send_exit(ticker, algotest_quantity(contract["lot_size"]))
            print(f"[ALGOTEST] EXIT SENT {ticker} | LOTS=1 | HTTP={result['status_code']} | REASON={reason}")
        else:
            print("[ALGOTEST] EXIT SKIPPED | FORWARD_TEST_ENABLE_ENTRIES=false")
        state.exit_sent = True
        state.entered = False
        write_trade_ledger(symbol, state)
        print(
            f"[RESULT] {symbol} {state.setup.side} | OPTION={contract['symbol']} | "
            f"ENTRY={state.option_entry_ltp:.2f} | EXIT={state.option_exit_ltp if state.option_exit_ltp is not None else 0:.2f} | "
            f"TARGET={state.target if state.target is not None else 0:.2f} | RESULT={reason}"
        )

    def on_open(wsapp):
        try:
            subscribe_stock_quotes()
            ws_ready.set()
        except Exception as exc:
            print(f"[SUBSCRIBE ERROR] {exc}")

    def on_data(wsapp, message):
        try:
            data = _parse_message(message)
            if not data:
                return
            token = str(data.get("token", ""))
            ltp = _ltp(data)
            if not token or ltp is None:
                return
            when = _event_time(data)
            if token in token_to_symbol and not freeze_done.is_set():
                symbol = token_to_symbol[token]
                close_raw = data.get("closed_price")
                if close_raw is not None:
                    try:
                        close = float(close_raw) / 100.0
                        if close > 0:
                            latest_quotes[token] = {"ltp": ltp, "close": close}
                    except (TypeError, ValueError):
                        pass
                collector.on_ltp(token, ltp, when)
                return

            if token in option_tokens:
                symbol, option_side = option_tokens[token]
                state = states.get(symbol)
                if not state or state.time_exit_reported:
                    return
                wanted = "CE" if state.setup.side == "LONG" else "PE"
                if option_side != wanted:
                    return
                previous = state.option_ltp
                state.option_ltp = ltp
                if not state.entered:
                    # Before entry we are waiting for the first option LTP.
                    # After a completed/closed trade, do not create another entry.
                    if state.trade_used or state.exit_sent:
                        return
                    if not should_print_option_ltp(previous, ltp):
                        return
                    send_entry(symbol, state, ltp)
                    return
                if state.target is not None and ltp >= state.target and not state.target_reported:
                    state.target_reported = True
                    send_exit(symbol, state, "TARGET_9_5PCT", ltp)
                return

            if freeze_done.is_set() and token in token_to_symbol:
                symbol = token_to_symbol[token]
                state = states.get(symbol)
                if not state or state.invalidated or state.time_exit_reported or state.trade_used:
                    return
                stock_ltp = ltp
                setup = state.setup
                if not state.entered:
                    hit_sl = (setup.side == "LONG" and stock_ltp <= setup.stock_sl) or (setup.side == "SHORT" and stock_ltp >= setup.stock_sl)
                    crossed = (setup.side == "LONG" and stock_ltp >= setup.entry_level) or (setup.side == "SHORT" and stock_ltp <= setup.entry_level)
                    if hit_sl and not crossed:
                        state.invalidated = True
                        print(f"[INVALIDATED] {symbol} {setup.side} | stock={stock_ltp:.2f} | SL={setup.stock_sl:.2f}")
                    elif crossed:
                        subscribe_options(symbol)
                        wanted = "ce" if setup.side == "LONG" else "pe"
                        contract = state.locked_option[wanted]
                        print(f"[STOCK TRIGGER] {symbol} {setup.side} | stock={stock_ltp:.2f} | entry={setup.entry_level:.2f} | option={contract['symbol']} | STATUS=WAIT_OPTION_LTP")
                else:
                    hit_sl = (setup.side == "LONG" and stock_ltp <= setup.stock_sl) or (setup.side == "SHORT" and stock_ltp >= setup.stock_sl)
                    if hit_sl and not state.sl_reported:
                        state.sl_reported = True
                        send_exit(symbol, state, "STOCK_SL", state.option_ltp)
        except Exception as exc:
            print(f"[DATA ERROR] {exc}")

    def on_error(wsapp, error):
        print(f"[WEBSOCKET ERROR] {error} | SDK reconnect policy active")

    def on_close(wsapp):
        print("[WEBSOCKET CLOSED]")

    sws.on_open = on_open
    sws.on_data = on_data
    sws.on_error = on_error
    sws.on_close = on_close

    ws_thread = threading.Thread(target=sws.connect, daemon=True)
    ws_thread.start()
    if not ws_ready.wait(timeout=20):
        raise RuntimeError("WebSocket did not become ready before 09:15")

    target = datetime.combine(now.date(), FREEZE_TIME, tzinfo=IST)
    while datetime.now(IST) < target:
        time_mod.sleep(0.2)

    if collector.count() < len(token_map):
        missing = len(token_map) - collector.count()
        print(f"[SAFE STOP] 09:15 candle incomplete: {collector.count()}/{len(token_map)} stocks received; missing={missing}")
        try:
            sws.close_connection()
        except Exception:
            pass
        return

    rows = []
    for symbol, token in token_map.items():
        candle = collector.candle(token)
        quote = latest_quotes.get(token)
        if candle is None or quote is None:
            continue
        rows.append({"symbol": symbol, "token": token, "ltp": quote["ltp"], "close": quote["close"], "candle": candle})

    gainers, losers = rank_top_movers(rows)
    ranked = [(x, "LONG") for x in gainers] + [(x, "SHORT") for x in losers]
    if len(ranked) < 14:
        print(f"[SAFE STOP] Could not build full Top 7 + Top 7 snapshot: {len(ranked)} candidates")
        try:
            sws.close_connection()
        except Exception:
            pass
        return

    print("\n[LOCKED 09:16] Top 7 gainers + Top 7 losers | LOCAL 09:15 CANDLE")
    for row, side in ranked:
        try:
            o, h, l, c = row["candle"]
            setup = make_setup(row["symbol"], o, h, l, c, side)
            if setup is None:
                print(f"  {row['symbol']:<14} {side:<5} REJECTED 09:15 candle")
                continue
            locked_option = lock_option_contract(master, row["symbol"], row["ltp"], now.date())
            states[row["symbol"]] = LiveState(setup=setup, locked_option=locked_option)
            wanted = "ce" if side == "LONG" else "pe"
            contract = locked_option[wanted]
            print(
                f"  {row['symbol']:<14} {side:<5} READY stock_ltp_0916={row['ltp']:.2f} "
                f"stock_entry={setup.entry_level:.2f} stock_sl={setup.stock_sl:.2f} "
                f"ATM={locked_option['atm']:.2f} ATM-1={locked_option['strike']:.2f} option={contract['symbol']}"
            )
        except Exception as exc:
            print(f"  {row['symbol']:<14} {side:<5} ERROR {exc}")

    freeze_done.set()
    if not states:
        print("[STOP] No qualifying setups among locked 14")
        try:
            sws.close_connection()
        except Exception:
            pass
        return

    print(f"[READY] {len(states)} eligible setups. Live stock trigger monitoring active until 15:40 IST.")
    print("[READY] AlgoTest entry/exit path uses 1 lot and JSON webhook messages.")

    try:
        while datetime.now(IST).time() < TIME_EXIT:
            time_mod.sleep(0.5)
    finally:
        for symbol, state in states.items():
            state.time_exit_reported = True
            if state.entered:
                send_exit(symbol, state, "TIME_EXIT_15_40", state.option_ltp)
            elif not state.trade_used:
                print(f"[EXPIRED] {symbol} {state.setup.side} | no option entry before 15:40")
        try:
            sws.close_connection()
        except Exception:
            pass
        ws_thread.join(timeout=3)
        print("[STOP] 15:40 IST | runner closed cleanly")


if __name__ == "__main__":
    main()
