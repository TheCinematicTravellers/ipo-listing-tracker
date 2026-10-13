# FNO 1-Minute Top-10 ORB Forward Test

This is a **separate subsystem** for the 1-minute strategy. It does not modify the existing 15-minute F&O movers page or its data files.

## Strategy locked for this build

- Universe: the existing 208-stock `fno_universe.json`.
- At **09:16 IST**, rank all available stocks by change from the previous official close.
- Lock only the **Top 10 gainers** and **Top 10 losers**. No stock outside those 20 may qualify.
- For each locked stock, inspect the completed **09:15-09:16 1-minute candle**.
- Long candidate: `Open = Low`.
- Short candidate: `Open = High`.
- Candle body must be **>= 50% of the candle's total high-low range**.
- Long entry: price crosses the candle high.
- Short entry: price crosses the candle low.
- Before entry, if the opposite side is crossed first, the setup is **INVALIDATED** and cannot re-enter.
- Initial SL: opposite side of the setup candle.
- Target: **1R** (`R = entry - SL` for long, `R = SL - entry` for short).
- One trade maximum per stock per day.
- This build is **Forward Test only**. It has no Angel One order-placement code.

## Data architecture

Angel One SmartAPI is used for market data. The current SmartAPI documentation supports bulk market quotes for up to 50 NSE tokens per request and a 1 request/second limit, so 208 stocks can be sampled in five quote requests. The first-minute OHLC for the selected candidates is then read from the historical candle API. The scanner monitors only the locked candidates after 09:16.

## AlgoTest architecture

The scanner sends the entry message to the private AlgoTest Trade Signal webhook, for example:

`INFY buy 1`

The AlgoTest signal must remain in **Forward Test / Listening** mode. Forward Test simulates execution and does not send real broker orders.

> Do not put the webhook URL, Angel One API key, client credentials, PIN, or TOTP secret into GitHub files. Use environment variables on the machine that runs the scanner.

## Environment

Copy `config.example.env` to a local `.env` (never commit the `.env`).

Required Angel One variables:

- `ANGEL_API_KEY`
- `ANGEL_CLIENT_CODE`
- `ANGEL_PIN`
- `ANGEL_TOTP_SECRET`

Required AlgoTest variable:

- `ALGOTEST_WEBHOOK_URL`

Safety defaults:

- `ENABLE_ALGOTEST=false`
- `FORWARD_TEST_ONLY=true`
- `TRADE_QTY=1`

Set `ENABLE_ALGOTEST=true` only after the Forward Test signal is confirmed as **LISTENING**.

## Running

```bash
pip install -r requirements_1m.txt
python fno_1m/scanner.py
```

The process is intended to run continuously during NSE market hours. It performs the 09:16 lock once, then monitors the locked candidates. It does not poll all 208 stocks continuously after the lock.

## Important

This repository branch is for code/configuration only. A persistent runtime is still required to execute the scanner during market hours. GitHub Pages is not the execution engine.
