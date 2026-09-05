"""Safe intraday dry-run harness for the 14:40 candle.

Uses the existing forward_runner rules unchanged:
- 14:40 IST is the setup candle.
- 14:41 IST is the activation/start gate.
- Historical catch-up is disabled for this live dry-run.
- AlgoTest receives only forward-test dummy entries.
"""
from __future__ import annotations

import os
import time as time_mod
from datetime import datetime, time
from zoneinfo import ZoneInfo

os.environ["FORWARD_TEST_ENABLE_ENTRIES"] = "true"
os.environ.setdefault("FORWARD_TEST_ONLY", "true")

if os.getenv("FORWARD_TEST_ONLY", "true").lower() != "true":
    raise RuntimeError("Safety stop: FORWARD_TEST_ONLY must remain true")
if not os.getenv("ALGO_TEST_WEBHOOK_URL", "").strip():
    raise RuntimeError("Safety stop: ALGO_TEST_WEBHOOK_URL is not configured")

import forward_runner as runner

IST = ZoneInfo("Asia/Kolkata")
# 14:40 candle is complete at 14:41. Monitoring/activation begins at 14:41.
runner.ENTRY_TIME = time(14, 41)


def wait_until_1441():
    """Wait until 14:41 IST rather than exiting when launched early."""
    while True:
        now = datetime.now(IST)
        if now.time() >= runner.ENTRY_TIME:
            print(f"[14:41 TEST] Activation gate reached: {now:%H:%M:%S} IST")
            return
        remaining = (
            datetime.combine(now.date(), runner.ENTRY_TIME, tzinfo=IST) - now
        ).total_seconds()
        print(
            f"[WAIT] Activation starts at 14:41 IST. Current: {now:%H:%M:%S} IST | "
            f"remaining={max(0, int(remaining))}s"
        )
        time_mod.sleep(min(10, max(1, remaining)))


def candle_1440(api, token, day):
    """Fetch today's 14:40 one-minute candle for setup qualification."""
    last_error = None
    for attempt in range(1, runner.RATE_LIMIT_RETRIES + 1):
        try:
            runner._pace_candle_request()
            response = api.getCandleData({
                "exchange": "NSE",
                "symboltoken": str(token),
                "interval": "ONE_MINUTE",
                "fromdate": f"{day} 14:40",
                "todate": f"{day} 14:41",
            })
            if not response or not response.get("status", True):
                message = str(response)
                if runner.RateLimitError.is_rate_limit(message):
                    raise runner.RateLimitError(message)
                raise RuntimeError(f"14:40 candle failed for {token}: {response}")
            data = response.get("data") or []
            if not data:
                raise RuntimeError(f"No 14:40 candle for token {token}")
            c = data[0]
            return float(c[1]), float(c[2]), float(c[3]), float(c[4])
        except Exception as exc:
            last_error = exc
            if not runner.RateLimitError.is_rate_limit(str(exc)) or attempt >= runner.RATE_LIMIT_RETRIES:
                raise
            wait = runner.CANDLE_RATE_LIMIT_COOLDOWN_SECONDS * attempt
            print(
                f"[RATE LIMIT] token={token} retry {attempt}/{runner.RATE_LIMIT_RETRIES} "
                f"after {wait:.0f}s"
            )
            runner.time_mod.sleep(wait)
    raise RuntimeError(str(last_error))


runner.candle_0915 = candle_1440


def no_historical_catchup(*_args, **_kwargs):
    print("[FORWARD 14:41] Historical catch-up disabled for this intraday test")


runner.run_historical_catchup = no_historical_catchup


if __name__ == "__main__":
    print(
        "[14:41 TEST] Setup candle = 14:40 | Activation = 14:41 | "
        "AlgoTest entries = ENABLED | FORWARD_TEST_ONLY = true"
    )
    wait_until_1441()
    runner.main()
