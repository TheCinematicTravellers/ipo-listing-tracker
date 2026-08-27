"""Angel One live market-data adapter for the F&O 1m forward test.

DATA ONLY: this module never places broker orders.
It reuses the SmartAPI login/WebSocket pattern already proven in the
existing C:\\Users\\megha\\nse_fno_orb project.
"""
import csv
import json
import os
from typing import Iterable

import pyotp
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

NSE = 1
NFO = 2
LTP = 1

BASE_DIR = os.getenv("NSE_FNO_ORB_DIR", r"C:\Users\megha\nse_fno_orb")
MASTER_FILE = os.getenv("ANGEL_MASTER_FILE", os.path.join(BASE_DIR, "OpenAPIScripMaster.json"))
FNO_LIST_FILE = os.getenv("FNO_STOCK_LIST", os.path.join(BASE_DIR, "fno_stock_list.csv"))

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PIN = os.getenv("ANGEL_PIN")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")


def login():
    if not all([API_KEY, CLIENT_ID, PIN, TOTP_SECRET]):
        raise RuntimeError("Missing ANGEL_API_KEY / ANGEL_CLIENT_ID / ANGEL_PIN / ANGEL_TOTP_SECRET")
    api = SmartConnect(api_key=API_KEY)
    session = api.generateSession(CLIENT_ID, PIN, pyotp.TOTP(TOTP_SECRET).now())
    if not session or not session.get("status"):
        raise RuntimeError(f"Angel One login failed: {session}")
    print("[OK] Angel One login successful")
    return api, session["data"]["feedToken"]


def load_master():
    with open(MASTER_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_fno_symbols() -> list[str]:
    if not os.path.exists(FNO_LIST_FILE):
        raise FileNotFoundError(FNO_LIST_FILE)
    with open(FNO_LIST_FILE, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError("F&O stock list is empty")
    fields = {str(k).strip().lower(): k for k in rows[0]}
    symbol_key = next((fields[k] for k in ("symbol", "tradingsymbol", "stock") if k in fields), None)
    if not symbol_key:
        raise RuntimeError(f"Cannot find a symbol column in {FNO_LIST_FILE}")
    symbols: list[str] = []
    for row in rows:
        value = str(row.get(symbol_key, "")).strip().upper()
        if value:
            symbols.append(value.removesuffix("-EQ"))
    return list(dict.fromkeys(symbols))


def underlying_tokens(master: list[dict], symbols: Iterable[str]) -> dict[str, str]:
    wanted = {s.upper() for s in symbols}
    out: dict[str, str] = {}
    for row in master:
        if str(row.get("exch_seg", "")).upper() != "NSE":
            continue
        symbol = str(row.get("symbol", "")).upper()
        if symbol.endswith("-EQ") and symbol[:-3] in wanted and row.get("token"):
            out[symbol[:-3]] = str(row["token"])
    print(f"[OK] Universe requested: {len(wanted)} | NSE tokens found: {len(out)}")
    return out


def run_data_only():
    obj, feed_token = login()
    master = load_master()
    tokens = underlying_tokens(master, load_fno_symbols())
    if not tokens:
        raise RuntimeError("No NSE tokens resolved")

    token_to_symbol = {token: symbol for symbol, token in tokens.items()}
    sws = SmartWebSocketV2(obj.access_token, API_KEY, CLIENT_ID, feed_token)

    def on_data(wsapp, message):
        try:
            data = json.loads(message) if isinstance(message, str) else message
            token = str(data.get("token", ""))
            raw = data.get("last_traded_price")
            symbol = token_to_symbol.get(token)
            if symbol and raw is not None:
                print(f"[LTP] {symbol}: {float(raw) / 100.0:.2f}")
        except Exception as exc:
            print(f"[DATA ERROR] {exc}")

    def on_open(wsapp):
        print("[OK] WebSocket connected")
        token_values = list(tokens.values())
        # Split into chunks rather than sending one oversized subscription.
        for i in range(0, len(token_values), 50):
            sws.subscribe(
                f"fno_1m_data_only_{i // 50}",
                LTP,
                [{"exchangeType": NSE, "tokens": token_values[i:i + 50]}],
            )
        print(f"[OK] Subscribed to {len(token_values)} NSE F&O tokens | DATA ONLY | NO ORDERS")

    sws.on_data = on_data
    sws.on_open = on_open
    sws.on_error = lambda ws, error: print(f"[WEBSOCKET ERROR] {error}")
    sws.on_close = lambda ws: print("[WEBSOCKET CLOSED]")
    sws.connect()


if __name__ == "__main__":
    run_data_only()
