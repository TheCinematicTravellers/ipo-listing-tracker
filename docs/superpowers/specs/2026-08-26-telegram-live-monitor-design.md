# Telegram Live Monitor Design

## Goal
Add a server-side live monitor that automatically watches the existing F&O ORB scanner during market hours and sends one Telegram alert when a selected stock transitions from Pending to a non-pending state.

## Scope
- Monitor the existing Top 10 gainers and Top 10 losers scanner universe.
- Start at 09:30 IST and stop after the configured market-session end.
- Reuse the existing ORB state engine. No trading-rule changes.
- Alert only on `Pending -> Trade Active`, `Pending -> Target`, `Pending -> SL`, or `Pending -> Invalidated`.
- Deduplicate alerts so refreshes/retries cannot repeatedly notify for the same symbol/day/transition.
- Continue working without the website being open.

## Architecture
1. Vercel scheduled server-side monitor invokes the scanner at a fixed cadence during market hours.
2. The monitor obtains current Angel One data and evaluates the existing state engine.
3. Persistent state stores the last notified status for each symbol and trading day.
4. Telegram Bot API sends the notification using server-side environment variables for the bot token and destination chat ID.
5. The website remains unchanged as the human-facing dashboard.

## Telegram message
Each alert includes symbol, new status, direction, ORB entry level, SL, 0.4R target, and IST timestamp. Messages are concise and use the existing status icons.

## Reliability
- Telegram failures must not alter scanner status.
- Angel/API failures must not generate false status-change alerts.
- State writes occur only after a Telegram send succeeds, preventing silent loss of an alert.
- Duplicate scheduled invocations are harmless because the persisted state is checked before sending.

## Configuration
Environment variables:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- Existing Angel One credentials remain server-side.

## Testing
- Unit tests for every Pending-to-status transition.
- Deduplication test for repeated monitor runs.
- Test that API failure produces no Telegram alert.
- Test that Telegram failure does not advance persisted alert state.
- Manual production smoke test with a controlled transition.
