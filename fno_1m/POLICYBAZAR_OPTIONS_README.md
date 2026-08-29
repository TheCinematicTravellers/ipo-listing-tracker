# Policybazaar Options Backtest

This pipeline translates the frozen Policybazaar S1 stock dataset into historical ATM monthly-expiry option trades using Upstox Plus expired-instrument APIs.

## Frozen stock input

`C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_S1_FINAL_BODY_GT20_QTY100_90TRADES.csv`

Rules are unchanged: 90 trades, body >20%, Tuesday/Wednesday/Thursday only, entry before 10:00 IST, Monday/Friday excluded, and the existing stock-side 1R/SL/3:05 PM unresolved exit.

## Upstox

- Underlying key: `NSE_EQ|INE417T01026`
- Historical contracts: `/v2/expired-instruments/option/contract`
- Historical candles: `/v2/expired-instruments/historical-candle/{expired_instrument_key}/5minute/{to_date}/{from_date}`
- Authentication: `UPSTOX_ACCESS_TOKEN` environment variable.
- Do not commit the token.

## Option mapping

- LONG stock signal -> nearest paired ATM monthly CE.
- SHORT stock signal -> nearest paired ATM monthly PE.
- Historical expired instrument key is preserved in the manifest.
- One option lot is used; the actual historical POLICYBZR lot size is read from the contract response.
- Option entry is the first 5-minute option candle strictly after the stock signal timestamp, using that candle OPEN to avoid look-ahead.

## Primary result

The primary option P&L is **stock-driven**. The option is entered from the stock signal and exited at the option close corresponding to the frozen stock trade's exit timestamp. This is the clean answer to: "How did the frozen S1 stock strategy translate into option rupees?"

The pipeline also reports an explicitly secondary option-driven sensitivity using a configurable premium stop percentage (default 50%) and a 1R target. It is not the frozen strategy's official result.

## Expiry-week buckets

Buckets are based on **calendar days remaining** until the selected monthly expiry, because the stock calendar file may end before the option expiry date:

- `WEEK_1`: more than 21 calendar days remaining.
- `WEEK_2`: 15-21 calendar days remaining.
- `WEEK_3`: 8-14 calendar days remaining.
- `EXPIRY_WEEK`: 0-7 calendar days remaining.

This is deliberately a time-to-expiry classification rather than a calendar-week label because the study is specifically testing option premium decay.

## Run

```powershell
cd C:\Users\megha\ipo-listing-tracker\fno_1m

$env:UPSTOX_ACCESS_TOKEN="YOUR_FRESH_UPSTOX_PLUS_TOKEN"

python run_policybazar_options.py `
  --stock-csv "C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_S1_FINAL_BODY_GT20_QTY100_90TRADES.csv" `
  --calendar-csv "C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_5m.csv" `
  --mode all
```

If you rerun after a partial download, existing contract and candle caches are reused.

## Outputs

Under `fno_1m/data/policybazar_options/`:

- `upstox_manifest.csv`
- `contract_cache/*.json`
- `raw_upstox/*/candles.csv`
- `trades.csv`
- `weekly_summary_stock_driven.csv`
- `weekly_summary_option_driven.csv`
- `monthly_summary_stock_driven.csv`
- `monthly_summary_option_driven.csv`
- `long_short_summary.csv`
- `data_quality.csv`
- `final_summary.csv`
