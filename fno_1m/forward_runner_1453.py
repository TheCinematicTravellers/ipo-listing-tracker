"""14:53 forward-only dry-run using locally built 14:52 candle.

Critical design change: the setup candle is built from the Angel WebSocket,
not getCandleData(). This removes the historical-candle API burst at activation.
The existing strategy, option locking, 9.5% target, stock SL and AlgoTest
forward-only entry path are reused unchanged from forward_runner.py.
"""
from __future__ import annotations

import os
import threading
import time as time_mod
from datetime import datetime, time
from zoneinfo import ZoneInfo

os.environ["FORWARD_TEST_ENABLE_ENTRIES"] = "true"
os.environ["FORWARD_TEST_ONLY"] = "true"

if not os.getenv("ALGO_TEST_WEBHOOK_URL", "").strip():
    raise RuntimeError("Safety stop: ALGO_TEST_WEBHOOK_URL is not configured")

import forward_runner as runner
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

IST = ZoneInfo("Asia/Kolkata")
SETUP_START = time(14, 52)
ACTIVATION = time(14, 53)


class MinuteCandleCollector:
    """Build one-minute OHLC candles directly from live LTP ticks."""

    def __init__(self, minute: str):
        self.minute = minute
        self._bars: dict[str, list[float]] = {}

    def on_ltp(self, token: str, ltp: float, when: datetime) -> None:
        if when.astimezone(IST).strftime("%H:%M") != self.minute:
            return
        values = self._bars.setdefault(str(token), [])
        values.append(float(ltp))

    def candle(self, token: str):
        values = self._bars.get(str(token), [])
        if not values:
            return None
        return values[0], max(values), min(values), values[-1]


def should_collect_minute(when: datetime) -> bool:
    local = when.astimezone(IST).time()
    return SETUP_START <= local < ACTIVATION


def wait_until_setup():
    while True:
        now = datetime.now(IST)
        if now.time() >= SETUP_START:
            return
        remaining = (
            datetime.combine(now.date(), SETUP_START, tzinfo=IST) - now
        ).total_seconds()
        print(
            f"[WAIT] Local setup collection starts 14:52 IST. "
            f"Current: {now:%H:%M:%S} IST | remaining={max(0, int(remaining))}s"
        )
        time_mod.sleep(min(10, max(1, remaining)))


def collect_setup_candles(api, feed_token, api_key, client_id, master, symbols):
    """Subscribe to all NSE stocks and build the 14:52 candle locally."""
    token_map = runner.nse_tokens(master, symbols)
    collector = MinuteCandleCollector("14:52")
    done = threading.Event()
    sws = SmartWebSocketV2(api.access_token, api_key, client_id, feed_token)

    def on_open(wsapp):
        tokens = list(token_map.values())
        for i in range(0, len(tokens), 50):
            sws.subscribe(
                f"setup_1453_{i // 50}",
                runner.LTP,
                [{"exchangeType": runner.NSE, "tokens": tokens[i:i + 50]}],
            )
        print(f"[LIVE FEED] Subscribed {len(tokens)} NSE stocks for 14:52 candle")

    def on_data(wsapp, message):
        try:
            data = message
            if isinstance(message, str):
                import json
                data = json.loads(message)
            token = str(data.get("token", ""))
            raw = data.get("last_traded_price")
            if not token or raw is None:
                return
            now = datetime.now(IST)
            if should_collect_minute(now):
                collector.on_ltp(token, float(raw) / 100.0, now)
            elif now.time() >= ACTIVATION:
                done.set()
        except Exception as exc:
            print(f"[SETUP FEED ERROR] {exc}")

    def on_error(wsapp, error):
        print(f"[SETUP FEED ERROR] {error}")

    sws.on_data = on_data
    sws.on_open = on_open
    sws.on_error = on_error
    sws.on_close = lambda wsapp: None
    sws.connect()

    while datetime.now(IST).time() < ACTIVATION:
        time_mod.sleep(0.25)

    try:
        sws.close_connection()
    except Exception:
        pass

    print(f"[LOCAL CANDLE] 14:52 candle collection complete | stocks with ticks={len(collector._bars)}")
    return collector, token_map


def install_local_candle_path(collector: MinuteCandleCollector):
    """Replace the historical 09:15 candle call with the locally built candle."""
    def local_candle(_api, token, _day):
        candle = collector.candle(str(token))
        if candle is None:
            raise RuntimeError(f"No live 14:52 candle collected for token {token}")
        return candle

    runner.candle_0915 = local_candle
    runner.run_historical_catchup = lambda *_args, **_kwargs: print(
        "[FORWARD 14:53] Historical catch-up disabled; live test starts from 14:53"
    )
    runner.ENTRY_TIME = ACTIVATION


def main():
    wait_until_setup()

    api, feed_token = runner.login()
    master = runner.load_master()
    symbols = runner.load_symbols()
    print(f"[OK] Real F&O universe: {len(runner.nse_tokens(master, symbols))}")
    print("[TEST] Setup candle: 14:52-14:53 | Activation: 14:53 IST")
    print("[TEST] Candle source: LIVE WEBSOCKET | Historical candle API: DISABLED")
    print("[OK] AlgoTest forward-only webhook configured")

    collector, _token_map = collect_setup_candles(
        api,
        feed_token,
        runner.API_KEY,
        runner.CLIENT_ID,
        master,
        symbols,
    )
    install_local_candle_path(collector)

    now = datetime.now(IST)
    if now.time() < ACTIVATION:
        time_mod.sleep(max(0, (datetime.combine(now.date(), ACTIVATION, tzinfo=IST) - now).total_seconds()))

    print(f"[LOCK] Activation reached: {datetime.now(IST):%H:%M:%S} IST")
    runner.main()


if __name__ == "__main__":
    main()
