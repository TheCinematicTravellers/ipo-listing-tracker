from __future__ import annotations

import csv
import json
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pyotp
import requests
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

IST = ZoneInfo("Asia/Kolkata")
NSE = 1
NFO = 2
LTP_MODE = 1
QUOTE_MODE = 2
LIVE_ENTRY_START = time(9, 15)
ORB_END = time(9, 20)
BREAKOUT_CUTOFF = time(10, 0)
TIME_EXIT = time(15, 5)
ONE_LOT = 1
ENABLE_ENTRIES = os.getenv("POLICYBAZAR_ENABLE_ENTRIES", "false").lower() == "true"
FORWARD_TEST_ONLY = os.getenv("FORWARD_TEST_ONLY", "true").lower() == "true"
POLICYBAZAR_WEBHOOK = os.getenv("POLICYBAZAR_ALGO_TEST_WEBHOOK_URL", "").strip()
BASE_DIR = os.getenv("NSE_FNO_ORB_DIR", r"C:\Users\megha\nse_fno_orb")
MASTER_FILE = os.getenv("ANGEL_MASTER_FILE", os.path.join(BASE_DIR, "OpenAPIScripMaster.json"))
API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PIN = os.getenv("ANGEL_PIN")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")
STOCK_SYMBOL = "POLICYBZR"


def is_trading_day(day: date) -> bool:
    return day.weekday() in (1, 2, 3)


def breakout_allowed(when: time) -> bool:
    return ORB_END <= when < BREAKOUT_CUTOFF


def stock_target_at_1r(side: str, entry: float, stock_sl: float) -> float:
    side = str(side).upper()
    if entry <= 0 or stock_sl <= 0:
        raise ValueError("entry and stock_sl must be positive")
    if side == "LONG":
        return entry + (entry - stock_sl)
    if side == "SHORT":
        return entry - (stock_sl - entry)
    raise ValueError("side must be LONG or SHORT")


def stock_exit_reason(side: str, stock_ltp: float, entry: float, stock_sl: float, target: float) -> str | None:
    side = str(side).upper()
    if side == "LONG":
        if stock_ltp <= stock_sl:
            return "STOCK_SL"
        if stock_ltp >= target:
            return "STOCK_1R"
    elif side == "SHORT":
        if stock_ltp >= stock_sl:
            return "STOCK_SL"
        if stock_ltp <= target:
            return "STOCK_1R"
    else:
        raise ValueError("side must be LONG or SHORT")
    return None


def option_entry_price(live_ltp: float) -> float:
    value = float(live_ltp)
    if value <= 0:
        raise ValueError("live option LTP must be positive")
    return value


def _expiry(value: object) -> date | None:
    text = str(value or "").strip().upper()
    for fmt in ("%d%b%Y", "%d%b%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _strike(value: object) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v / 100.0 if v > 0 else None


def resolve_atm(master: list[dict], stock_ltp: float, today: date) -> dict:
    """Select the nearest actual paired CE/PE strike for nearest monthly expiry."""
    candidates = []
    for row in master:
        if str(row.get("exch_seg", "")).upper() != "NFO":
            continue
        if str(row.get("instrumenttype", "")).upper() != "OPTSTK":
            continue
        name = str(row.get("name", "")).upper()
        symbol = str(row.get("symbol", "")).upper()
        if name != STOCK_SYMBOL and not symbol.startswith(STOCK_SYMBOL):
            continue
        exp = _expiry(row.get("expiry"))
        strike = _strike(row.get("strike"))
        cp = symbol[-2:]
        if exp is None or exp < today or strike is None or cp not in {"CE", "PE"} or not row.get("token"):
            continue
        candidates.append((exp, strike, cp, row))
    if not candidates:
        raise RuntimeError("No POLICYBZR OPTSTK contracts found")
    expiry = min(x[0] for x in candidates)
    rows = [x for x in candidates if x[0] == expiry]
    paired: dict[float, dict[str, dict]] = {}
    for _, strike, cp, row in rows:
        paired.setdefault(strike, {})[cp] = row
    strikes = sorted(s for s, legs in paired.items() if "CE" in legs and "PE" in legs)
    if not strikes:
        raise RuntimeError(f"No paired POLICYBZR strikes for {expiry}")
    strike = min(strikes, key=lambda s: abs(s - stock_ltp))
    return {
        "expiry": expiry.strftime("%d%b%Y").upper(),
        "strike": strike,
        "ce": {"symbol": paired[strike]["CE"]["symbol"], "token": str(paired[strike]["CE"]["token"]), "lot_size": int(float(paired[strike]["CE"].get("lotsize") or 0))},
        "pe": {"symbol": paired[strike]["PE"]["symbol"], "token": str(paired[strike]["PE"]["token"]), "lot_size": int(float(paired[strike]["PE"].get("lotsize") or 0))},
    }


def algotest_symbol(expiry: str, strike: float, cp: str) -> str:
    d = datetime.strptime(expiry, "%d%b%Y")
    return f"{STOCK_SYMBOL}{d:%y%m%d}{'C' if cp == 'CE' else 'P'}{strike:g}"


def send_algotest(ticker: str, action: str) -> None:
    if not FORWARD_TEST_ONLY:
        raise RuntimeError("Safety stop: FORWARD_TEST_ONLY must remain true")
    if not POLICYBAZAR_WEBHOOK:
        raise RuntimeError("POLICYBAZAR_ALGO_TEST_WEBHOOK_URL is not configured")
    payload = f"{ticker} {action} {ONE_LOT}"
    response = requests.post(POLICYBAZAR_WEBHOOK, json=payload, timeout=10)
    if not response.ok:
        raise RuntimeError(f"AlgoTest webhook rejected: HTTP {response.status_code}: {response.text}")
    print(f"[ALGOTEST] {action.upper()} SENT | {ticker} | LOTS=1 | HTTP={response.status_code}")


def load_master() -> list[dict]:
    with open(MASTER_FILE, encoding="utf-8") as f:
        return json.load(f)


def login():
    if not all([API_KEY, CLIENT_ID, PIN, TOTP_SECRET]):
        raise RuntimeError("Missing Angel credentials")
    api = SmartConnect(api_key=API_KEY)
    session = api.generateSession(CLIENT_ID, PIN, pyotp.TOTP(TOTP_SECRET).now())
    if not session or not session.get("status"):
        raise RuntimeError(f"Angel One login failed: {session}")
    return api, session["data"]["feedToken"]


def _ltp(message: dict) -> float | None:
    try:
        value = float(message.get("last_traded_price")) / 100.0
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _when(message: dict) -> datetime:
    raw = message.get("exchange_timestamp")
    try:
        return datetime.fromtimestamp(float(raw) / 1000.0, IST)
    except (TypeError, ValueError, OSError):
        return datetime.now(IST)


def main() -> None:
    now = datetime.now(IST)
    if not is_trading_day(now.date()):
        print(f"[SAFE STOP] POLICYBZR disabled on {now:%A}; Tuesday-Thursday only.")
        return
    if now.time() >= TIME_EXIT:
        print("[SAFE STOP] POLICYBZR runner started after 15:05 IST")
        return
    if now.time() >= LIVE_ENTRY_START:
        print("[SAFE STOP] Start this runner before 09:15 IST; no historical 09:15 reconstruction.")
        return

    api, feed_token = login()
    master = load_master()
    stock_rows = [r for r in master if str(r.get("exch_seg", "")).upper() == "NSE" and str(r.get("symbol", "")).upper() == "POLICYBZR-EQ"]
    if not stock_rows:
        raise RuntimeError("POLICYBZR-EQ not found in Angel master")
    stock_token = str(stock_rows[0]["token"])

    sws = SmartWebSocketV2(api.access_token, API_KEY, CLIENT_ID, feed_token, max_retry_attempt=5, retry_strategy=1, retry_delay=2, retry_multiplier=2, retry_duration=5)
    orb_values: list[float] = []
    stock_last: float | None = None
    option_last: float | None = None
    state: dict | None = None
    option_token: str | None = None

    def on_open(wsapp):
        sws.subscribe("policybzar_stock", QUOTE_MODE, [{"exchangeType": NSE, "tokens": [stock_token]}])
        print("[LIVE] POLICYBZR subscribed | building 09:15-09:20 ORB")

    def on_data(wsapp, message):
        nonlocal stock_last, option_last, state, option_token
        if not isinstance(message, dict):
            return
        value = _ltp(message)
        if value is None:
            return
        token = str(message.get("token", ""))
        when = _when(message)
        t = when.time()

        if token == stock_token:
            stock_last = value
            if LIVE_ENTRY_START <= t < ORB_END:
                orb_values.append(value)
                return
            if state is None and breakout_allowed(t) and len(orb_values) >= 2:
                high = max(orb_values)
                low = min(orb_values)
                if value > high:
                    side = "LONG"
                elif value < low:
                    side = "SHORT"
                else:
                    return
                sl = low if side == "LONG" else high
                target = stock_target_at_1r(side, value, sl)
                contract = resolve_atm(master, value, when.date())
                cp = "CE" if side == "LONG" else "PE"
                option_token = contract[cp.lower()]["token"]
                state = {"side": side, "entry": value, "sl": sl, "target": target, "contract": contract, "cp": cp, "option_entry": None, "entry_sent": False, "exit_sent": False}
                print(f"[SIGNAL] POLICYBZR {side} | STOCK={value:.2f} | SL={sl:.2f} | 1R={target:.2f} | ATM={contract['strike']:.2f} | EXP={contract['expiry']}")
                sws.subscribe("policybzar_option", LTP_MODE, [{"exchangeType": NFO, "tokens": [option_token]}])
                print(f"[LIVE] Option subscribed: {contract[cp.lower()]['symbol']}")
                return
            if state is not None and state["entry_sent"] and not state["exit_sent"]:
                reason = stock_exit_reason(state["side"], value, state["entry"], state["sl"], state["target"])
                if reason:
                    state["exit_sent"] = True
                    exit_ltp = option_last if option_last is not None else state["option_entry"]
                    print(f"[EXIT] {reason} | STOCK={value:.2f} | OPTION={exit_ltp}")
                    if ENABLE_ENTRIES:
                        send_algotest(algotest_symbol(state["contract"]["expiry"], state["contract"]["strike"], state["cp"]), "sell")
                    return
            if state is not None and state["entry_sent"] and not state["exit_sent"] and t >= TIME_EXIT:
                state["exit_sent"] = True
                print(f"[EXIT] TIME_15:05 | OPTION={option_last}")
                if ENABLE_ENTRIES:
                    send_algotest(algotest_symbol(state["contract"]["expiry"], state["contract"]["strike"], state["cp"]), "sell")
            return

        if state is None or option_token is None or token != option_token or state["exit_sent"]:
            return
        option_last = option_entry_price(value)
        if not state["entry_sent"]:
            state["option_entry"] = option_last
            state["entry_sent"] = True
            print(f"[OPTION ENTRY] {state['contract'][state['cp'].lower()]['symbol']} | LIVE LTP={option_last:.2f} | LIMIT BUY @ LTP | LOTS=1")
            if ENABLE_ENTRIES:
                send_algotest(algotest_symbol(state["contract"]["expiry"], state["contract"]["strike"], state["cp"]), "buy")

    def on_error(wsapp, error):
        print(f"[WS ERROR] {error}")

    def on_close(wsapp, code, reason):
        print(f"[WS CLOSED] code={code} reason={reason}")

    sws.on_open = on_open
    sws.on_data = on_data
    sws.on_error = on_error
    sws.on_close = on_close
    print(f"[MODE] PolicyBZR AlgoTest forwarding: {'ENABLED' if ENABLE_ENTRIES else 'DISABLED'}")
    print("[ISOLATION] This runner uses POLICYBAZAR_ALGO_TEST_WEBHOOK_URL and does not touch forward_runner.py")
    sws.connect()


if __name__ == "__main__":
    main()
