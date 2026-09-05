import os
from datetime import datetime

import requests


class AlgoTestForward:
    def __init__(self, timeout: int = 10):
        self.url = os.getenv("ALGO_TEST_WEBHOOK_URL", "").strip()
        self.forward_only = os.getenv("FORWARD_TEST_ONLY", "true").lower() == "true"
        self.timeout = timeout

    @staticmethod
    def build_payload(symbol: str, side: str, lots: int = 1) -> str:
        """Build the documented AlgoTest Trade Signal message.

        The webhook quantity is LOTS for our F&O signal. AlgoTest expands the
        lot count using the instrument's lot size. Production default is one lot.
        """
        action = "buy" if side in {"LONG", "BUY"} else "sell"
        if int(lots) < 1:
            raise ValueError("lots must be >= 1")
        return f"{symbol} {action} {int(lots)}"

    def send_entry(self, symbol: str, side: str, quantity: int = 1) -> dict:
        if not self.forward_only:
            raise RuntimeError("Safety stop: FORWARD_TEST_ONLY must remain true")
        if not self.url:
            raise RuntimeError("ALGO_TEST_WEBHOOK_URL is not configured")
        payload = self.build_payload(symbol, side, quantity)
        response = requests.post(self.url, json=payload, timeout=self.timeout)
        if not response.ok:
            raise RuntimeError(
                f"AlgoTest webhook rejected entry: HTTP {response.status_code}: {response.text}"
            )
        return {"status_code": response.status_code, "payload": payload}

    def send_exit(self, symbol: str, quantity: int = 1) -> dict:
        if not self.forward_only:
            raise RuntimeError("Safety stop: FORWARD_TEST_ONLY must remain true")
        if not self.url:
            raise RuntimeError("ALGO_TEST_WEBHOOK_URL is not configured")
        payload = self.build_payload(symbol, "SHORT", quantity)
        response = requests.post(self.url, json=payload, timeout=self.timeout)
        if not response.ok:
            raise RuntimeError(
                f"AlgoTest webhook rejected exit: HTTP {response.status_code}: {response.text}"
            )
        return {"status_code": response.status_code, "payload": payload}
