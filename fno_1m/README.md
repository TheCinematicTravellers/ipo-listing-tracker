# F&O 1M Forward Test

Isolated subsystem. The existing 15-minute Top Gainer/Loser website is intentionally untouched.

## Locked strategy
- Universe: existing 208 real F&O stocks. Dummy `NSETEST` symbols are excluded.
- Maximum eligible stock price: **₹20,000**.
- At 09:16 IST, rank eligible stocks by change vs previous official close.
- Lock Top 7 Gainers and Top 7 Losers. No later additions.
- Setup candle: 09:15-09:16, 1 minute.
- Gainers: Open=Low and total candle body >= 50% -> LONG candidate.
- Losers: Open=High and total candle body >= 50% -> SHORT candidate.
- If the opposite level is crossed before entry, invalidate.
- Stock is the signal/risk instrument; the traded instrument is the current nearest-expiry ATM option.
- LONG stock signal -> ATM CE. SHORT stock signal -> ATM PE.
- Option entry is a LIMIT BUY at the first live option LTP after stock entry.
- Option target = entry option LTP * 1.095 (+9.5%).
- Exit immediately if underlying stock hits its original stock SL.
- Exit any open option at 15:05 IST if neither target nor stock SL occurred.
- Forward test only. No direct Angel One order-placement call exists in this subsystem.

## Live components
- `angel_live.py`: proven Angel One login + NSE 1-minute market-data transport, data-only.
- `run_data_only.py`: safe smoke-test entrypoint; no AlgoTest calls and no orders.
- `option_feed.py`: resolves nearest-expiry ATM CE/PE, token and lot size from the Angel instrument master.
- `forward_runner.py`: locks Top 7/7 at 09:16, validates the 09:15 setup, dynamically subscribes to the ATM option feed, and can forward an entry to AlgoTest only when `FORWARD_TEST_ENABLE_ENTRIES=true`.

## Important safety state
`FORWARD_TEST_ENABLE_ENTRIES` defaults to `false`.

AlgoTest exit integration is intentionally **not** guessed. The existing `algotest.py` still refuses to send exits until the documented exit webhook contract is wired. Keep entries disabled until the full entry + exit path is tested.

## Safety
Keep all credentials and the private AlgoTest webhook/API URL in environment variables or the runtime secret store. Never commit secrets.
