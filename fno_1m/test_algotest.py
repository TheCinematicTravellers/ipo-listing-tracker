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
