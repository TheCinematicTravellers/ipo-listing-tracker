# F&O 1-Minute Scanner

This is an isolated internal scanner. **Do not modify the existing `fno_movers.html` / 15-minute Top Movers workflow.**

## Locked rules

- Universe: `fno_universe.json` (208 NSE F&O stocks).
- Build the first 1-minute candle from Angel One WebSocket ticks: 09:15:00–09:15:59 IST.
- At 09:16, rank all available stocks by first-candle close versus the previous official close.
- Lock exactly the Top 10 Gainers and Top 10 Losers.
- Gainer setup: first candle `Open = Low` and body/range `>= 50%` -> LONG.
- Loser setup: first candle `Open = High` and body/range `>= 50%` -> SHORT.
- LONG entry = first candle high; SL = first candle low.
- SHORT entry = first candle low; SL = first candle high.
- Before entry, crossing the opposite level first invalidates the setup.
- After entry, first Target/SL hit determines the result.
- Target is configurable with `FNO_1M_TARGET_R`; default is `0.5R` while the target is still being evaluated.
- No new stocks are admitted after the 09:16 lock.

## Live runtime

Run `scanner.py` on the static-IP server/VEE. **Do not run the live scanner from GitHub Actions**: the strategy needs a persistent WebSocket connection and sub-minute event handling.

Required environment variables:

```text
ANGEL_API_KEY
ANGEL_CLIENT_CODE
ANGEL_PIN
ANGEL_TOTP_SECRET
TELEGRAM_BOT_TOKEN   # optional
TELEGRAM_CHAT_ID     # optional
FNO_1M_TARGET_R      # optional, default 0.5
```

Install:

```bash
pip install -r requirements_1m.txt
cd fno_1m
python scanner.py
```

The scanner writes `fno_1m/state.json`. The read-only dashboard is `fno_1m/index.html` and is intentionally separate from the existing 15-minute page.

## Safety

The scanner currently **does not place Angel One orders**. It only detects setups, tracks entry/invalidated/Target/SL state, and can send Telegram alerts. Order execution will be added only after the live signal path is verified.
