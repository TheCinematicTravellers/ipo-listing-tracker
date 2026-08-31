from __future__ import annotations

import csv
import json
import os
import threading
import time as time_mod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pyotp
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

from algotest import AlgoTestCashForward
from strategy import DEFAULT_QTY, IST_OPEN, SHORT_TRIGGER_TIME, SHORT_TRIGGER_END, LONG_CUTOFF_TIME, LONG_START_TIME, TIME_EXIT, OpeningCandle, TradeState, build_short_setup, build_long_setup, exit_reason

IST = ZoneInfo("Asia/Kolkata")
NSE = 1
LTP = 1
STOCK_SYMBOL = "SWIGGY"
EQ_SYMBOL = "SWIGGY-EQ"
BASE_DIR = Path(__file__).resolve().parent
LEDGER = BASE_DIR / "logs" / "swiggy_cash_trade_ledger.csv"
STATE_FILE = BASE_DIR / "state.json"
API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PIN = os.getenv("ANGEL_PIN")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")
MASTER_FILE = os.getenv("ANGEL_MASTER_FILE", r"C:\Users\megha\Stocks backtest\Swiggy\OpenAPIScripMaster.json")
ENABLE_ALGOTEST = os.getenv("SWIGGY_ENABLE_ALGOTEST", "false").lower() == "true"
FORWARD_TEST_ONLY = os.getenv("FORWARD_TEST_ONLY", "true").lower() == "true"
QTY = int(os.getenv("SWIGGY_TRADE_QTY", str(DEFAULT_QTY)))

@dataclass
class RuntimeState:
    candle: OpeningCandle | None = None
    first_break: str | None = None
    setup: TradeState | None = None
    entered: bool = False
    entry_price: float | None = None
    entry_time: str | None = None
    last_price: float | None = None
    exit_price: float | None = None
    exit_time: str | None = None
    exit_reason: str | None = None
    order_entry_sent: bool = False
    order_exit_sent: bool = False
    finished: bool = False

def login():
    if not all([API_KEY, CLIENT_ID, PIN, TOTP_SECRET]):
        raise RuntimeError("Missing ANGEL_API_KEY / ANGEL_CLIENT_ID / ANGEL_PIN / ANGEL_TOTP_SECRET")
    api = SmartConnect(api_key=API_KEY)
    session = api.generateSession(CLIENT_ID, PIN, pyotp.TOTP(TOTP_SECRET).now())
    if not session or not session.get("status"):
        raise RuntimeError(f"Angel One login failed: {session}")
    return api, session["data"]["feedToken"]

def load_stock_token() -> str:
    with open(MASTER_FILE, encoding="utf-8") as f:
        master = json.load(f)
    rows = [r for r in master if str(r.get("exch_seg", "")).upper() == "NSE" and str(r.get("symbol", "")).upper() == EQ_SYMBOL and r.get("token")]
    if not rows:
        raise RuntimeError(f"{EQ_SYMBOL} not found in Angel instrument master")
    return str(rows[0]["token"])

def event_time(message: dict) -> datetime:
    raw = message.get("exchange_timestamp")
    if raw is not None:
        try:
            return datetime.fromtimestamp(float(raw) / 1000.0, IST)
        except (TypeError, ValueError, OSError):
            pass
    return datetime.now(IST)

def ltp(message: dict) -> float | None:
    try:
        value = float(message.get("last_traded_price")) / 100.0
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None

def write_state(state: RuntimeState, status: str):
    payload = {"date_ist": datetime.now(IST).date().isoformat(), "updated_ist": datetime.now(IST).isoformat(timespec="seconds"), "symbol": STOCK_SYMBOL, "qty": QTY, "mode": "ALGOTEST_FORWARD_ONLY" if ENABLE_ALGOTEST else "PAPER_FORWARD_TEST", "status": status, "price": state.last_price, "opening_candle": None if state.candle is None else vars(state.candle), "first_break": state.first_break, "side": None if state.setup is None else state.setup.side, "entry": state.entry_price, "stop": None if state.setup is None else state.setup.stop, "target": None if state.setup is None else state.setup.target, "entry_time": state.entry_time, "exit": state.exit_price, "exit_time": state.exit_time, "exit_reason": state.exit_reason}
    STATE_FILE.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

def ensure_ledger():
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    if LEDGER.exists():
        return
    with LEDGER.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["date", "symbol", "side", "qty", "entry_time", "entry_price", "stock_sl", "stock_target_1R", "exit_time", "exit_price", "exit_reason", "gross_pnl_rupees", "status"])

def write_ledger(state: RuntimeState):
    if not state.entered or state.entry_price is None or state.exit_price is None or state.setup is None:
        return
    pnl_per_share = state.exit_price - state.entry_price if state.setup.side == "LONG" else state.entry_price - state.exit_price
    pnl = pnl_per_share * QTY
    status = "WIN" if state.exit_reason == "STOCK_1R" else "SL" if state.exit_reason == "STOCK_SL" else "TIME_EXIT"
    with LEDGER.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([datetime.now(IST).date().isoformat(), STOCK_SYMBOL, state.setup.side, QTY, state.entry_time or "", f"{state.entry_price:.2f}", f"{state.setup.stop:.2f}", f"{state.setup.target:.2f}", state.exit_time or "", f"{state.exit_price:.2f}", state.exit_reason or "", f"{pnl:.2f}", status])

def send_entry(bridge: AlgoTestCashForward, state: RuntimeState, price: float):
    state.entry_price = price
    state.entry_time = datetime.now(IST).isoformat(timespec="seconds")
    state.entered = True
    # Keep the approved S1 ORB entry/SL/1R levels. The live tick only triggers the order.
    state.setup = build_short_setup(state.candle) if state.first_break == "SHORT" else build_long_setup(state.candle)
    action = "buy" if state.setup.side == "LONG" else "sell"
    if ENABLE_ALGOTEST:
        result = bridge.send(STOCK_SYMBOL, action, QTY)
        print(f"[ALGOTEST] ENTRY SENT | {result['message']} | HTTP={result['status_code']}")
    else:
        print(f"[PAPER] ENTRY | {STOCK_SYMBOL} {state.setup.side} {QTY} @ {price:.2f}")
    state.order_entry_sent = True
    write_state(state, "ACTIVE")

def send_exit(bridge: AlgoTestCashForward, state: RuntimeState, reason: str, price: float):
    if not state.entered or state.order_exit_sent:
        return
    state.exit_price = price
    state.exit_time = datetime.now(IST).isoformat(timespec="seconds")
    state.exit_reason = reason
    if ENABLE_ALGOTEST:
        action = "sell" if state.setup.side == "LONG" else "buy"
        result = bridge.send(STOCK_SYMBOL, action, QTY)
        print(f"[ALGOTEST] EXIT SENT | {result['message']} | HTTP={result['status_code']} | REASON={reason}")
    else:
        print(f"[PAPER] EXIT | {STOCK_SYMBOL} {state.setup.side} {QTY} @ {price:.2f} | {reason}")
    state.order_exit_sent = True
    state.finished = True
    write_ledger(state)
    write_state(state, reason)

def main():
    if not FORWARD_TEST_ONLY:
        raise RuntimeError("Safety stop: FORWARD_TEST_ONLY must remain true")
    if QTY <= 0:
        raise RuntimeError("SWIGGY_TRADE_QTY must be positive")
    now = datetime.now(IST)
    if now.weekday() >= 5:
        print("[SAFE STOP] NSE closed for weekend")
        return
    if now.time() >= TIME_EXIT:
        print("[SAFE STOP] Runner started after 15:13 IST")
        return
    if now.time() >= IST_OPEN:
        print("[SAFE STOP] Start runner before 09:15 IST so the opening candle is built live")
        return
    api, feed_token = login()
    stock_token = load_stock_token()
    bridge = AlgoTestCashForward()
    state = RuntimeState()
    ensure_ledger()
    ws = SmartWebSocketV2(api.access_token, API_KEY, CLIENT_ID, feed_token)
    lock = threading.Lock()

    def on_open(wsapp):
        wsapp.subscribe("swiggy_cash_s1", LTP, [{"exchangeType": NSE, "tokens": [stock_token]}])
        print("[LIVE] SWIGGY subscribed | building 09:15 opening candle")
        print(f"[MODE] {'ALGOTEST FORWARD TEST' if ENABLE_ALGOTEST else 'PAPER FORWARD TEST'} | CASH | QTY={QTY}")
        print("[RULE] SHORT: first 09:15 low break in 09:20-09:24:59")
        print("[RULE] LONG: Tuesday first 09:15 high break 09:20-09:59:59")

    def on_data(wsapp, message):
        price = ltp(message) if isinstance(message, dict) else None
        if price is None:
            return
        when = event_time(message) if isinstance(message, dict) else datetime.now(IST)
        if when.date() != now.date():
            return
        t = when.time()
        with lock:
            state.last_price = price
            if state.finished:
                return
            if IST_OPEN <= t < SHORT_TRIGGER_TIME:
                if state.candle is None:
                    state.candle = OpeningCandle(price, price, price, price)
                else:
                    state.candle = OpeningCandle(state.candle.open, max(state.candle.high, price), min(state.candle.low, price), price)
                write_state(state, "BUILDING_09_15")
                return
            if state.candle is None:
                return
            if not state.entered and state.first_break is None and t >= SHORT_TRIGGER_TIME:
                if price < state.candle.low:
                    state.first_break = "SHORT"
                    if t < SHORT_TRIGGER_END:
                        send_entry(bridge, state, price)
                    else:
                        state.finished = True
                        write_state(state, "SHORT_WINDOW_EXPIRED")
                    return
                if price > state.candle.high:
                    if now.weekday() == 1 and LONG_START_TIME <= t < LONG_CUTOFF_TIME:
                        state.first_break = "LONG"
                        send_entry(bridge, state, price)
                    else:
                        state.first_break = "LONG_NOT_ELIGIBLE"
                        state.finished = True
                        write_state(state, "LONG_NOT_ELIGIBLE")
                    return
            if state.entered and state.setup is not None:
                reason = exit_reason(state.setup.side, price, state.setup.stop, state.setup.target, t)
                if reason:
                    send_exit(bridge, state, reason, price)

    def on_error(wsapp, error): print(f"[WS ERROR] {error}")
    def on_close(wsapp, code, reason): print(f"[WS CLOSED] code={code} reason={reason}")
    ws.on_open = on_open
    ws.on_data = on_data
    ws.on_error = on_error
    ws.on_close = on_close
    thread = threading.Thread(target=ws.connect, daemon=True)
    thread.start()
    try:
        while datetime.now(IST).time() < TIME_EXIT and not state.finished:
            time_mod.sleep(0.25)
    finally:
        with lock:
            if state.entered and state.setup is not None:
                last = state.last_price if state.last_price is not None else state.entry_price
                send_exit(bridge, state, "TIME_EXIT_15_13", float(last))
            elif not state.finished:
                state.finished = True
                write_state(state, "NO_TRADE")
        try: ws.close_connection()
        except Exception: pass
        thread.join(timeout=3)
        print("[STOP] SWIGGY cash S1 runner stopped")

if __name__ == "__main__":
    main()
