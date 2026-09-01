from algotest import AlgoTestCashForward


def test_long_cash_entry_message():
    assert AlgoTestCashForward.build_message("SWIGGY", "buy", 1000) == "SWIGGY buy 1000"


def test_short_cash_entry_message():
    assert AlgoTestCashForward.build_message("SWIGGY", "sell", 1000) == "SWIGGY sell 1000"


def test_long_exit_is_cash_sell():
    assert AlgoTestCashForward.build_message("SWIGGY", "sell", 1000) == "SWIGGY sell 1000"


def test_short_exit_is_cash_buy():
    assert AlgoTestCashForward.build_message("SWIGGY", "buy", 1000) == "SWIGGY buy 1000"
