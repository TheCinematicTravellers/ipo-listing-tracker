import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from algotest import AlgoTestForward


def test_algotest_entry_payload_is_one_lot_buy():
    assert AlgoTestForward.build_payload("RELIANCE260929C1280", "LONG", 1) == "RELIANCE260929C1280 buy 1"


def test_algotest_exit_payload_is_one_lot_sell():
    assert AlgoTestForward.build_payload("RELIANCE260929C1280", "SHORT", 1) == "RELIANCE260929C1280 sell 1"


def test_algotest_payload_rejects_zero_lots():
    try:
        AlgoTestForward.build_payload("RELIANCE260929C1280", "LONG", 0)
    except ValueError:
        return
    raise AssertionError("zero lots must be rejected")
def test_algotest_entry_returns_response_body(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "accepted"

        @property
        def ok(self):
            return True

    monkeypatch.setenv("ALGO_TEST_WEBHOOK_URL", "https://example.invalid/test")
    monkeypatch.setenv("FORWARD_TEST_ONLY", "true")

    monkeypatch.setattr(
        "algotest.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = AlgoTestForward().send_entry(
        "RELIANCE260929C1280",
        "LONG",
        1,
    )

    assert result["response"] == "accepted"

def test_algotest_log_includes_response_body():
    from forward_runner import format_algotest_result

    result = {
        "status_code": 200,
        "payload": "RELIANCE260929C1280 buy 1",
        "response": "accepted",
    }

    message = format_algotest_result("ENTRY", "RELIANCE260929C1280", result)

    assert "HTTP=200" in message
    assert "RESPONSE=accepted" in message