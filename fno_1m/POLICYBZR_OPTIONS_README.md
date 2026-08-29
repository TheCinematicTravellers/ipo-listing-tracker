# POLICYBZR Monthly Options Research Pipeline

This pipeline sits on top of the finalized POLICYBZR S1 stock strategy.

## Stock signal locked for this research

- Tuesday, Wednesday, Thursday only.
- First 5-minute candle at 09:15 defines ORB high/low.
- First break of ORB high = LONG; first break of ORB low = SHORT.
- Breakout must occur before 10:00 IST.
- Stock SL = opposite side of first candle.
- Stock 1R = original first-candle high-low range.
- Unresolved stock trade exits at the 15:05 candle close.

## Option mapping

- LONG stock signal -> BUY ATM monthly-expiry CE.
- SHORT stock signal -> BUY ATM monthly-expiry PE.
- Monthly expiry is selected from actual Angel OPTSTK contracts on/after the signal date.
- ATM is the nearest actual paired CE/PE strike to the stock breakout price.
- No strike interval is guessed.

## Historical option entry limitation

The stock signal is intrabar, but the first research dataset uses 5-minute option candles. To avoid look-ahead, the default option entry is the OPEN of the first option candle strictly after the stock breakout timestamp. A future 1-minute option-data version can tighten this approximation without changing the contract manifest.

## Two exit models

### Stock-driven
Option is entered from the stock signal and exits when the stock hits 1R, stock SL, or the 15:05 stock close. The option exit price is the close of the option candle aligned to the stock exit timestamp.

### Option-driven
Option is entered the same way, then uses an explicitly configured option stop percentage. Option target is one option-risk unit above entry. Unresolved option trades exit at 15:05. The option stop percentage is a research parameter and is NOT a finalized trading rule.

## Commands

Build contract manifest:

`python run_policybazar_options.py --stock-csv C:\path\POLICYBZR_5m.csv --master C:\path\OpenAPIScripMaster.json --mode manifest`

Download targeted option history:

`python run_policybazar_options.py --stock-csv C:\path\POLICYBZR_5m.csv --master C:\path\OpenAPIScripMaster.json --mode download`

Run both backtests with a 50% option stop research parameter:

`python run_policybazar_options.py --stock-csv C:\path\POLICYBZR_5m.csv --master C:\path\OpenAPIScripMaster.json --mode backtest --option-stop-pct 50`

Generate expiry-week reports:

`python run_policybazar_options.py --stock-csv C:\path\POLICYBZR_5m.csv --master C:\path\OpenAPIScripMaster.json --mode report`

Or run the full pipeline with `--mode all`.

## Output

- `data/policybazar_options/manifest.csv`
- `data/policybazar_options/raw/<token>/candles.csv`
- `data/policybazar_options/trades.csv`
- `data/policybazar_options/weekly_summary_stock_driven.csv`
- `data/policybazar_options/weekly_summary_option_driven.csv`
- `data/policybazar_options/data_quality.csv`

Keep the raw option cache. It is part of the reproducibility record for this research.
