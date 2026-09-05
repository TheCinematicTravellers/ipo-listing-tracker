"""Safe intraday dry-run harness for the 14:40 candle.

Keeps every strategy rule in forward_runner.py unchanged. The only timing
change is:
- setup candle: 14:40-14:41 IST 1-minute candle
- runner activation gate: 14:45 IST
- option contract is locked from the current stock LTP at runner start
- normal stock trigger, option entry, 9.5% target, stock SL and 15:05 exit
  logic remain in forward_runner.py

AlgoTest entries are forced ON for this harness, but FORWARD_TEST_ONLY must
remain true. No live broker order is sent by this script.
"""
from __future__ import annotations

import os
from datetime import time

# Force this harness into AlgoTest forward-test mode before importing the
# runner, because forward_runner reads these environment flags at import time.
os.environ["FORWARD_TEST_ENABLE_ENTRIES"] = "true"
os.environ.setdefault("FORWARD_TEST_ONLY", "true")

if os.getenv("FORWARD_TEST_ONLY", "true").lower() != "true":
    raise RuntimeError("Safety stop: FORWARD_TEST_ONLY must remain true")
if not os.getenv("ALGO_TEST_WEBHOOK_URL", "").strip():
    raise RuntimeError("Safety stop: ALGO_TEST_WEBHOOK_URL is not configured")

import forward_runner as runner


# User-approved live-test timing: use the completed 14:40 candle and start
# evaluating stock triggers from 14:45, leaving a five-minute safety buffer.
runner.ENTRY_TIME = time(14, 45)


def candle_1440(api, token, day):
    """Fetch only today's 14:40 one-minute candle for setup qualification."""
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
            print(f"[RATE LIMIT] token={token} retry {attempt}/{runner.RATE_LIMIT_RETRIES} after {wait:.0f}s")
            runner.time_mod.sleep(wait)
    raise RuntimeError(str(last_error))


# Reuse the existing main flow and every existing strategy/exit rule.
runner.candle_0915 = candle_1440

# This is a forward test, not a historical replay. Starting at 14:45 should
# never reconstruct the morning session or create retroactive entries.
def no_historical_catchup(*_args, **_kwargs):
    print("[FORWARD 14:45] Historical catch-up disabled for this intraday test")


runner.run_historical_catchup = no_historical_catchup

print("[14:45 TEST] Setup candle = 14:40 | AlgoTest entries = ENABLED | FORWARD_TEST_ONLY = true")
runner.main()
