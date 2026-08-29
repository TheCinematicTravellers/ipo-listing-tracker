# Policybazaar Options Data Provenance

## Source

- Stock signal CSV: `C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_S1_FINAL_BODY_GT20_QTY100_90TRADES.csv`
- Stock 5-minute calendar/exits CSV: `C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_5m.csv`
- Upstox underlying: `NSE_EQ|INE417T01026`
- Contract source: Upstox Plus expired option contract API.
- Candle source: Upstox Plus expired historical candle API, 5-minute interval.

## Historical contract rule

The resolver uses the historical individual-security monthly-expiry schedule: Thursday legacy expiry through August 2025, then last Tuesday from September 2025, moving to the previous trading day when the expiry Tuesday is a holiday. The Upstox expired-contract API is the final authority: candidate dates are tested until a historical contract set is returned.

## ATM rule

Select the nearest strike among strikes that have both CE and PE contracts for the selected historical expiry. Ties choose the lower strike. LONG uses CE; SHORT uses PE.

## Timing rule

Because the stock breakout can occur inside a 5-minute bar, option entry uses the first option candle strictly after the stock signal timestamp and that candle's OPEN. This avoids look-ahead.

## Exit rule

Primary result exits the option using the option CLOSE corresponding to the frozen stock strategy's exit timestamp. If the frozen stock trade resolves before the option can be entered, the trade is marked `STOCK_EXIT_BEFORE_OPTION_ENTRY` rather than inventing an option fill.

## Integrity rule

Never substitute a current contract for an expired historical contract. Missing historical contracts or missing candles remain explicit data-quality statuses.

## Cache

- `contract_cache/`: raw Upstox expired-contract responses, one JSON per expiry.
- `raw_upstox/`: 5-minute candle cache, one CSV per historical expired instrument key.

The cache is intentionally retained so the 15-day Upstox Plus trial is used efficiently and reruns do not repeatedly consume API access.
