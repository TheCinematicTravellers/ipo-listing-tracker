"""Live 1-minute F&O forward-test scanner using Angel One SmartAPI WebSocket V2.

IMPORTANT: this program is deliberately signal-only. It has no broker order
method and refuses to start unless DRY_RUN is true. It is isolated from the
existing 15-minute mover system.
"""
import json
import os
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pyotp
import requests
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

from strategy import Setup, body_pct, qualify

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parent
UNIVERSE_FILE = ROOT.parent / "fno_universe.json"
STATE_FILE = ROOT / "state.json"
MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
TARGET_R = float(os.getenv("FNO_1M_TARGET_R", "0.5"))
MIN_BODY_PCT = 50.0
TOP_N = 10
DRY_RUN = os.getenv("DRY_RUN", "true").strip().lower() in {"1", "true", "yes", "on"}


def load_universe():
    symbols = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
    if len(symbols) != 208:
        raise RuntimeError(f"Expected 208 F&O symbols, found {len(symbols)}")
    return symbols


def load_master():
    return requests.get(MASTER_URL, timeout=30).json()


def build_tokens(master, symbols):
    by_symbol = {}
    for row in master:
        if str(row.get("exch_seg", "")).upper() != "NSE":
            continue
        sym = str(row.get("symbol", ""))
        if sym.endswith("-EQ"):
            by_symbol[sym[:-3]] = str(row.get("token"))
    missing = [s for s in symbols if s not in by_symbol]
    if missing:
        raise RuntimeError("Missing NSE EQ tokens: " + ", ".join(missing))
    return {s: by_symbol[s] for s in symbols}


def login():
    api = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
    result = api.generateSession(
        os.environ["ANGEL_CLIENT_CODE"],
        os.environ["ANGEL_PIN"],
        pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"]).now(),
    )
    if not result.get("status"):
        raise RuntimeError(f"Angel login failed: {result}")
    return api, result["data"]


def previous_closes(api, tokens):
    """Fetch the previous official close used for the 09:16 mover ranking."""
    out = {}
    items = list(tokens.items())
    for i in range(0, len(items), 50):
        batch = items[i : i + 50]
        data = api.getMarketData("OHLC", {"NSE": [token for _, token in batch]})
        if not data.get("status"):
            raise RuntimeError(f"Angel quote failed: {data}")
        for row in data.get("data", {}).get("fetched", []):
            token = str(row.get("symbolToken"))
            if row.get("close") is not None:
                out[token] = float(row["close"])
        time.sleep(1.05)
    missing = [s for s, t in tokens.items() if t not in out]
    if missing:
        raise RuntimeError("Missing previous closes: " + ", ".join(missing))
    return out


def telegram(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text},
            timeout=15,
        ).raise_for_status()
    except Exception as exc:
        print(f"Telegram error: {exc}")


class Engine:
    def __init__(self, symbols, token_map, prev_close, ws=None):
        self.symbols = symbols
        self.token_map = token_map
        self.token_to_symbol = {v: k for k, v in token_map.items()}
        self.prev_close = prev_close
        self.candles = {}
        self.locked = []
        self.setups = {}
        self.locked_once = False
        self.ws = ws

    def tick(self, msg):
        token = str(msg.get("token", ""))
        symbol = self.token_to_symbol.get(token)
        if not symbol or msg.get("last_traded_price") is None:
            return

        price = float(msg["last_traded_price"]) / 100.0
        ts_ms = int(msg.get("exchange_timestamp") or int(time.time() * 1000))
        ts = datetime.fromtimestamp(ts_ms / 1000, IST)
        now = datetime.now(IST)
        if ts.date() != now.date() or ts.time() < dtime(9, 15) or ts.time() >= dtime(15, 30):
            return

        # Build the 09:15 candle only. The first tick at/after 09:16 freezes it.
        if ts.time() < dtime(9, 16):
            c = self.candles.setdefault(
                symbol, {"open": price, "high": price, "low": price, "close": price}
            )
            c["high"] = max(c["high"], price)
            c["low"] = min(c["low"], price)
            c["close"] = price

        if not self.locked_once and ts.time() >= dtime(9, 16):
            self.lock_universe()

        if self.locked_once and symbol in self.setups:
            setup = self.setups[symbol]
            old = setup.status
            new = setup.on_price(price, ts.strftime("%H:%M:%S"))
            if new != old:
                self.publish(symbol, setup)

    def lock_universe(self):
        if self.locked_once:
            return

        # We rank the stocks for which a complete 09:15 candle was received.
        # A missing tick cannot invent a mover; any missing symbols are reported.
        rows = []
        for symbol, c in self.candles.items():
            token = self.token_map[symbol]
            prev = self.prev_close.get(token)
            if prev and c["high"] >= c["low"]:
                change = (c["close"] / prev - 1) * 100
                rows.append((symbol, change, dict(c)))

        if len(rows) < TOP_N * 2:
            raise RuntimeError(f"Only {len(rows)} stocks had a 09:15 candle at lock; need at least 20")

        gainers = sorted(rows, key=lambda x: x[1], reverse=True)[:TOP_N]
        losers = sorted(rows, key=lambda x: x[1])[:TOP_N]
        self.locked = [x[0] for x in gainers + losers]
        self.locked_once = True

        for symbol, _, c in gainers:
            if qualify(c["open"], c["high"], c["low"], c["close"], "LONG", MIN_BODY_PCT):
                self.setups[symbol] = Setup(
                    symbol, "LONG", **c,
                    body_pct=body_pct(**c), target_r=TARGET_R,
                )
        for symbol, _, c in losers:
            if qualify(c["open"], c["high"], c["low"], c["close"], "SHORT", MIN_BODY_PCT):
                self.setups[symbol] = Setup(
                    symbol, "SHORT", **c,
                    body_pct=body_pct(**c), target_r=TARGET_R,
                )

        if self.ws:
            keep_tokens = {self.token_map[s] for s in self.locked}
            drop = [t for t in self.token_map.values() if t not in keep_tokens]
            if drop:
                for i in range(0, len(drop), 1000):
                    self.ws.unsubscribe(
                        "fno1m-drop", 1,
                        [{"exchangeType": 1, "tokens": drop[i : i + 1000]}],
                    )

        self.write_state(gainers, losers)
        telegram(self.lock_message(gainers, losers))

    def lock_message(self, gainers, losers):
        g = ", ".join(f"{s} {p:+.2f}%" for s, p, _ in gainers)
        l = ", ".join(f"{s} {p:+.2f}%" for s, p, _ in losers)
        setups = ", ".join(f"{s} {x.side} PENDING" for s, x in self.setups.items()) or "None"
        return (
            "📡 1M F&O LOCKED @ 09:16\n\n"
            f"🟢 Top 10 Gainers\n{g}\n\n"
            f"🔴 Top 10 Losers\n{l}\n\n"
            f"✅ Qualifying setups\n{setups}\n"
            f"Target: {TARGET_R}R\nMODE: FORWARD TEST / NO ORDERS"
        )

    def publish(self, symbol, setup):
        labels = {
            "ACTIVE": "✅ Trade Active",
            "TARGET": "🎯 Target",
            "SL": "❌ SL",
            "INVALIDATED": "⚠️ Invalidated",
        }
        telegram(
            f"{labels[setup.status]}\n{symbol}\n{setup.side}\n"
            f"Entry: {setup.entry}\nSL: {setup.sl}\nTarget: {setup.target}\n"
            f"Time: {setup.entry_time or setup.result_time or setup.invalidation_time}\n"
            "MODE: FORWARD TEST / NO ORDERS"
        )
        self.write_state()

    def write_state(self, gainers=None, losers=None):
        data = {
            "updated_ist": datetime.now(IST).strftime("%d-%b-%Y %H:%M:%S"),
            "mode": "FORWARD_TEST_NO_ORDERS",
            "target_r": TARGET_R,
            "body_min_pct": MIN_BODY_PCT,
            "locked": self.locked,
            "gainers": [s for s, _, _ in gainers] if gainers else [],
            "losers": [s for s, _, _ in losers] if losers else [],
            "setups": {s: vars(x) for s, x in self.setups.items()},
        }
        STATE_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def main():
    if not DRY_RUN:
        raise RuntimeError("Safety lock: set DRY_RUN=true. This scanner is forward-test only.")

    now = datetime.now(IST)
    if now.weekday() >= 5:
        return
    symbols = load_universe()
    token_map = build_tokens(load_master(), symbols)
    api, data = login()
    prev = previous_closes(api, token_map)
    ws = SmartWebSocketV2(
        data["jwtToken"],
        os.environ["ANGEL_API_KEY"],
        os.environ["ANGEL_CLIENT_CODE"],
        data["feedToken"],
        max_retry_attempt=5,
    )
    engine = Engine(symbols, token_map, prev, ws)

    def on_open(wsapp):
        wsapp.subscribe("fno1m", 1, [{"exchangeType": 1, "tokens": list(token_map.values())}])
        telegram("🟢 1M F&O scanner connected\nWaiting for 09:15 candle...\nMODE: FORWARD TEST / NO ORDERS")

    ws.on_open = on_open
    ws.on_data = lambda wsapp, message: engine.tick(message)
    ws.on_error = lambda wsapp, error: telegram(f"🔴 1M scanner error\n{error}")
    ws.on_close = lambda wsapp: telegram("🔴 1M scanner disconnected")
    ws.connect()


if __name__ == "__main__":
    main()
