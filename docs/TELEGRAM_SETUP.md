# Telegram live monitor setup

The live ORB monitor runs server-side and does not require the scanner page to be open.

## Required Vercel environment variables

- `TELEGRAM_BOT_TOKEN`: token from BotFather
- `TELEGRAM_CHAT_ID`: destination chat/group/channel ID
- `UPSTASH_REDIS_REST_URL`: Upstash Redis REST endpoint
- `UPSTASH_REDIS_REST_TOKEN`: Upstash Redis REST token
- `SCANNER_BASE_URL`: production scanner URL, for example `https://our-screener.vercel.app`

## Behavior

The Vercel cron invokes `/api/telegram-monitor` every minute during the NSE monitoring window. The monitor reads the existing scanner endpoint, stores the last status for each symbol in Redis, and sends exactly one Telegram alert when a symbol transitions from `⏳ Pending` to a different status.

State is stored with a one-day expiry so a new trading day starts cleanly.

## Telegram setup

1. Create a Telegram bot with BotFather and copy its token.
2. Send the bot a message from the destination chat/group, then obtain that chat ID.
3. Create an Upstash Redis database and copy its REST URL/token.
4. Add the five variables above to the Vercel project for Production.
5. Redeploy after adding variables.

No broker credentials or Telegram credentials are stored in GitHub.
