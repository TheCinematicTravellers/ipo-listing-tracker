from __future__ import annotations

import os
import requests


class AlgoTestCashForward:
    """Forward-Test-only bridge for SWIGGY cash equity signals."""

    def __init__(self) -> None:
        self.url = os.getenv("SWIGGY_ALGOTEST_WEBHOOK_URL", "").strip()
        self.enabled = os.getenv("SWIGGY_ENABLE_ALGOTEST", "false").lower() == "true"
        self.forward_only = os.getenv("FORWARD_TEST_ONLY", "true").lower() == "true"
        self.qty = int(os.getenv("SWIGGY_TRADE_QTY", "1000"))
        if self.qty <= 0:
            raise ValueError("SWIGGY_TRADE_QTY must be positive")
        if self.enabled and not self.forward_only:
            raise RuntimeError("Safety stop: SWIGGY bridge supports Forward Test only")
        if self.enabled and not self.url:
            raise RuntimeError("SWIGGY_ALGOTEST_WEBHOOK_URL is required when enabled")

    @staticmethod
    def build_message(symbol: str, action: str, qty: int = 1000) -> str:
        action = action.lower()
        if action not in {"buy", "sell"}:
            raise ValueError("action must be buy or sell")
        if int(qty) <= 0:
            raise ValueError("qty must be positive")
        return f"{symbol.upper()} {action} {int(qty)}"

    def send(self, symbol: str, action: str, qty: int | None = None) -> dict:
        quantity = self.qty if qty is None else int(qty)
        message = self.build_message(symbol, action, quantity)
        if not self.enabled:
            return {"sent": False, "dry_run": True, "message": message}
        response = requests.post(
            self.url,
            json=message,
            timeout=10,
        )
        response.raise_for_status()
        return {"sent": True, "dry_run": False, "status_code": response.status_code, "message": message, "response": response.text[:500]}
