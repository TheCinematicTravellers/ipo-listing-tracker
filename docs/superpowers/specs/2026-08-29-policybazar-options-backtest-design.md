# Policybazaar Upstox Options Backtest Design

**Date:** 2026-08-29

## Goal

Measure how the frozen 90-trade Policybazaar S1 stock signals would have performed when expressed as ATM monthly-expiry options, using Upstox Plus expired-contract and expired-5-minute-candle APIs.

## Frozen stock input

- Authoritative input: `POLICYBZR_S1_FINAL_BODY_GT20_QTY100_90TRADES.csv`.
- Exactly 90 trades.
- Body > 20%.
- Tuesday, Wednesday, Thursday only.
- Entry before 10:00 IST.
- Monday and Friday excluded.
- Existing stock-side 1R/SL/3:05 PM unresolved logic remains unchanged.
- No new stock-entry optimization is introduced.

## Option mapping

- Underlying: `NSE_EQ|INE417T01026` (POLICYBZR).
- For each signal, select the first monthly expiry on or after the signal date.
- Resolve historical contracts through Upstox `/v2/expired-instruments/option/contract`.
- Select the paired CE/PE strike nearest the stock entry price.
- LONG signal maps to CE; SHORT signal maps to PE.
- Preserve the historical `expired_instrument_key`, trading symbol, strike, expiry, lot size, and exchange token in the manifest.

## Option candles

- Download historical 5-minute candles through Upstox `/v2/expired-instruments/historical-candle/...`.
- Use a local cache keyed by expired instrument key.
- A stock breakout may occur inside its 5-minute bar, so option entry uses the first option candle strictly after the stock signal timestamp and its OPEN. This avoids look-ahead.

## Exits and reporting

The primary performance view is **stock-driven**: the option is entered from the stock signal and exits when the frozen stock trade exits; the option price at that exit is used for option P&L. This directly answers how the frozen stock strategy translated into option rupees.

A secondary, explicitly labeled **option-driven scenario** is retained as an exploratory sensitivity: option premium stop percentage is configurable (default 50%), with a 1R target on option premium risk and 3:05 PM unresolved exit. It must never be presented as the frozen stock strategy's official result.

Report separately:

- LONG vs SHORT.
- WEEK_1, WEEK_2, WEEK_3, and EXPIRY_WEEK.
- Monthly expiry.
- Individual trade ledger.
- Data quality and missing-data status.
- Net P&L, win rate, profit factor, average P&L, gross profit/loss, and max drawdown where applicable.

## Reproducibility

All resolved contracts, downloaded candles, trade outputs, summaries, and methodology must be stored under `fno_1m/data/policybazar_options/` and must be cacheable so reruns do not redownload existing candles.

No current contract may be substituted for a historical contract. Any missing historical contract or candle remains an explicit data-quality failure.
