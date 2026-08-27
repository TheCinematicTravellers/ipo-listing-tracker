import os
import requests


class AlgoTestForward:
    def __init__(self, timeout: int = 10):
        self.url = os.getenv("ALGO_TEST_WEBHOOK_URL", "").strip()
        self.forward_only = os.getenv("FORWARD_TEST_ONLY", "true").lower() == "true"
        self.timeout = timeout

    def send_entry(self, symbol: str, side: str, quantity: int) -> dict:
        if not self.forward_only:
            raise RuntimeError("Safety stop: FORWARD_TEST_ONLY must remain true")
        if not self.url:
            raise RuntimeError("ALGO_TEST_WEBHOOK_URL is not configured")
        action = "buy" if side == "LONG" else "buy"
        # AlgoTest Trade Signals message. The actual option symbol is supplied by caller.
        payload = f"{symbol} {action} {int(quantity)}"
        response = requests.post(self.url, data=payload, timeout=self.timeout)
        response.raise_for_status()
        return {"status_code": response.status_code, "payload": payload}

    def send_exit(self, symbol: str, quantity: int) -> dict:
        raise NotImplementedError("Do not guess an AlgoTest exit webhook contract; wire the documented exit mechanism before enabling exits.")
