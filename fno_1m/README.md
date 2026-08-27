# F&O 1M Forward Test

Isolated subsystem. The existing 15-minute Top Gainer/Loser website is intentionally untouched.

## Locked strategy
- Universe: existing F&O universe, excluding any stock with price > ₹10,000.
- At 09:16 IST, rank eligible stocks by change vs previous official close.
- Lock Top 7 Gainers and Top 7 Losers. No later additions.
- Setup candle: 09:15-09:16, 1 minute.
- Gainers: Open=Low and total candle body >= 50% -> LONG candidate.
- Losers: Open=High and total candle body >= 50% -> SHORT candidate.
- If the opposite level is crossed before entry, invalidate.
- Stock is the signal/risk instrument; the traded instrument is the current ATM option.
- LONG stock signal -> buy ATM CE. SHORT stock signal -> buy ATM PE.
- Option entry is a LIMIT BUY at the current option LTP.
- Option target = entry option LTP * 1.095 (+9.5%).
- Exit immediately if underlying stock hits its original stock SL.
- Exit any open option at 15:05 IST if neither target nor stock SL occurred.
- Forward test only. No direct Angel One order-placement call exists in this subsystem.

## Current implementation status
- `angel_live.py`: live Angel One login + NSE 1-minute market-data transport, data-only.
- `run_data_only.py`: safe smoke-test entrypoint; no AlgoTest calls and no orders.
- ATM/NFO option subscription will be integrated next from the proven existing local option-feed implementation.
- AlgoTest entry/exit integration will be enabled only after the option-token/LTP path is verified.

## Safety
Keep all credentials and the private AlgoTest webhook/API URL in environment variables or the runtime secret store. Never commit secrets.
