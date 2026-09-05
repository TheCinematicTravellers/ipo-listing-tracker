"""One-shot RELIANCE -> ATM option -> AlgoTest Forward Test bridge check.
Safety: sends only to ALGO_TEST_WEBHOOK_URL and requires FORWARD_TEST_ONLY=true.
"""
from __future__ import annotations
import os
from datetime import date
from forward_runner import login, load_master, nse_tokens, market_quote, lock_option_contract, NFO
from algotest import AlgoTestForward

def main():
    if os.getenv("FORWARD_TEST_ONLY", "true").lower() != "true":
        raise RuntimeError("Safety stop: FORWARD_TEST_ONLY must be true")
    if not os.getenv("ALGO_TEST_WEBHOOK_URL", "").strip():
        raise RuntimeError("ALGO_TEST_WEBHOOK_URL is not configured")
    api, _ = login()
    master = load_master()
    eq = nse_tokens(master, ["RELIANCE"])
    q = market_quote(api, eq.values())
    if not q:
        raise RuntimeError(f"No RELIANCE quote returned: {q}")
    item = next((x for x in q if str(x.get("tradingSymbol", x.get("symbol", ""))).upper().startswith("RELIANCE")), q[0])
    ltp = float(item.get("ltp") or item.get("lastTradedPrice") or 0)
    if ltp <= 0:
        raise RuntimeError(f"Could not read RELIANCE LTP: {item}")
    contracts = lock_option_contract(master, "RELIANCE", ltp, date.today())
    leg = contracts["ce"]
    oq = api.getMarketData("FULL", {"NFO": [str(leg["token"])]})
    if not isinstance(oq, dict) or not oq.get("status", True):
        raise RuntimeError(f"Option quote failed: {oq}")
    fetched = oq.get("data", {}).get("fetched", [])
    if not fetched:
        raise RuntimeError(f"No option quote returned: {oq}")
    oi = fetched[0]
    option_ltp = float(oi.get("ltp") or oi.get("lastTradedPrice") or 0)
    qty = int(leg["lot_size"])
    symbol = str(leg["symbol"])
    print(f"[RELIANCE] stock LTP={ltp:.2f}")
    print(f"[OPTION] expiry={contracts['expiry']} ATM={contracts['atm']:.2f} ATM-1={contracts['atm_minus_1']:.2f}")
    print(f"[OPTION] CE={symbol} token={leg['token']} LTP={option_ltp:.2f} lot={qty}")
    print(f"[ALGOTEST] Sending ONE FORWARD BUY: {symbol} buy {qty}")
    result = AlgoTestForward().send_entry(symbol, "LONG", qty)
    print(f"[ALGOTEST] SENT {result}")

if __name__ == "__main__":
    main()
