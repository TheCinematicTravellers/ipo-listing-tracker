from strategy import Side, State, candle_qualifies, make_setup


def test_body_filter():
    ok, pct = candle_qualifies(100, 110, 100, 105, 50)
    assert ok is True
    assert pct == 50.0

    ok, pct = candle_qualifies(100, 110, 100, 104.9, 50)
    assert ok is False
    assert pct < 50.0


def test_long_open_equals_low():
    setup = make_setup("TEST", "1", 2.0, ["09:15", 100, 110, 100, 108, 1000])
    assert setup is not None
    assert setup.side == Side.LONG
    assert setup.entry == 110
    assert setup.stop == 100
    assert setup.target == 120

    assert setup.process_price(105) is None
    assert setup.state == State.PENDING
    assert setup.process_price(99) == "INVALIDATED"


def test_long_entry_then_target():
    setup = make_setup("TEST", "1", 2.0, ["09:15", 100, 110, 100, 108, 1000])
    assert setup.process_price(110) == "ENTRY"
    assert setup.state == State.ACTIVE
    assert setup.entry_price == 110
    assert setup.process_price(120) == "TARGET"


def test_short_open_equals_high():
    setup = make_setup("TEST", "1", -2.0, ["09:15", 110, 110, 100, 102, 1000])
    assert setup is not None
    assert setup.side == Side.SHORT
    assert setup.entry == 100
    assert setup.stop == 110
    assert setup.target == 90
    assert setup.process_price(111) == "INVALIDATED"


def test_short_entry_then_sl():
    setup = make_setup("TEST", "1", -2.0, ["09:15", 110, 110, 100, 102, 1000])
    assert setup.process_price(100) == "ENTRY"
    assert setup.state == State.ACTIVE
    assert setup.process_price(110) == "SL"
