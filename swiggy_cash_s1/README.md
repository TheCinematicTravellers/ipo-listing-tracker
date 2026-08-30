# SWIGGY S1 Cash Intraday Forward Test

Isolated SWIGGY cash-equity runner based on the live Angel One + AlgoTest architecture used by the existing POLICYBAZAR runner. The uploaded POLICYBAZAR live runner uses SmartWebSocketV2, builds the opening candle from live ticks, maintains stock-side exits, and forwards signals through an isolated AlgoTest webhook. This SWIGGY module keeps that transport pattern but removes all option logic. 

## Final selected rules

### SHORT: all weekdays
- 09:15 IST first 5-minute candle defines the opening range.
- The first directional break decides the day.
- A SHORT is valid only when the 09:15 Low breaks during the **09:20-09:24:59** candle.
- Entry: live SWIGGY price when the low breaks.
- Stock SL: 09:15 High.
- Stock target: 1R from live entry to the stock SL.
- No body/Wyck filter, range filter, or close-based exit.

### LONG: Tuesday only
- Tuesday only.
- First 09:15 High break from **09:20 through 09:59:59** triggers LONG.
- If the 09:15 Low breaks first, the Tuesday LONG is no longer eligible. The first break wins.
- Entry: live SWIGGY price when the high breaks.
- Stock SL: 09:15 Low.
- Stock target: 1R from live entry to the stock SL.

## Position size

Default: **1,000 SWIGGY shares**.

Override with `SWIGGY_TRADE_QTY` without changing strategy logic.

## Execution

This is **cash equity only**. No CE/PE, no strikes, no ATM selection, no option LTP.

Entry messages sent to AlgoTest are:

- LONG: `SWIGGY buy 1000`
- SHORT: `SWIGGY sell 1000`

Exit messages are the opposite cash transaction:

- LONG exit: `SWIGGY sell 1000`
- SHORT exit: `SWIGGY buy 1000`

`SWIGGY_ENABLE_ALGOTEST=false` by default. `FORWARD_TEST_ONLY=true` is mandatory. The bridge never calls Angel One order placement.

## Intraday safety exit

The research baseline records unresolved trades at EOD. The live forward runner additionally closes any still-open cash position at **15:13 IST** so the AlgoTest Forward Test position is not intentionally carried beyond the intraday session.

## Runtime

A persistent machine/VEE is required. GitHub Actions is used for code validation, not as the live WebSocket runtime.

Required environment variables:

```text
ANGEL_API_KEY
ANGEL_CLIENT_ID
ANGEL_PIN
ANGEL_TOTP_SECRET
ANGEL_MASTER_FILE   # optional; defaults to C:\Users\megha\nse_fno_orb\OpenAPIScripMaster.json

FORWARD_TEST_ONLY=true
SWIGGY_ENABLE_ALGOTEST=false
SWIGGY_ALGOTEST_WEBHOOK_URL=
SWIGGY_TRADE_QTY=1000
```

Start the process **before 09:15 IST**. A late start is a safe stop because the runner does not reconstruct the 09:15 candle from historical data.

```powershell
cd C:\path\to\ipo-listing-tracker\swiggy_cash_s1
python live_runner.py
```

Before enabling the webhook, confirm the AlgoTest signal is configured for **Forward Test / Listening** and accepts the cash-equity signal format.

## Files

- `strategy.py`: pure SWIGGY timing, 1R, and exit rules.
- `algotest.py`: isolated cash Trade Signal bridge.
- `live_runner.py`: Angel One WebSocket live runner and state/ledger.
- `test_strategy.py`: rule-level tests.
- `state.json`: local runtime status, created when the runner runs.
- `logs/swiggy_cash_trade_ledger.csv`: completed forward-test trade ledger.
