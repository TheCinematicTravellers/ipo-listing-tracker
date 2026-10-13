from __future__ import annotations

import os
import requests


class AlgoTestForward:
    """Forward-Test-only entry bridge.

    This module deliberately has no broker/order-placement code. It only POSTs
    the simple Trade Signal message to the private AlgoTest webhook.
    """

    def __init__(self) -> None:
        self.url = os.getenv("ALGOTEST_WEBHOOK_URL", "").strip()
        self.enabled = os.getenv("ENABLE_ALGOTEST", "false").lower() == "true"
        self.forward_test_only = os.getenv("FORWARD_TEST_ONLY", "true").lower() == "true"
        self.qty = int(os.getenv("TRADE_QTY", "1"))

        if self.enabled and not self.forward_test_only:
            raise RuntimeError("Safety stop: this build only supports Forward Test mode.")
        if self.enabled and not self.url:
            raise RuntimeError("ALGOTEST_WEBHOOK_URL is required when ENABLE_ALGOTEST=true")

    def send_entry(self, symbol: str, side: str, qty: int | None = None) -> dict:
        quantity = qty if qty is not None else self.qty
        action = "buy" if side.upper() == "LONG" else "sell"
        message = f"{symbol} {action} {quantity}"

        if not self.enabled:
            return {"sent": False, "dry_run": True, "message": message}

        response = requests.post(
            self.url,
            data=message,
            headers={"Content-Type": "text/plain"},
            timeout=10,
        )
        response.raise_for_status()
        return {
            "sent": True,
            "dry_run": False,
            "status_code": response.status_code,
            "message": message,
            "response": response.text[:500],
        }
