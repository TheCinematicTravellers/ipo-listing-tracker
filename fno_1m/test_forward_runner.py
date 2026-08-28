from datetime import date

from forward_runner import RateLimitError, should_print_option_ltp, lock_option_contract


def test_rate_limit_error_is_detected():
    assert RateLimitError.is_rate_limit("Access denied because of exceeding access rate")
    assert RateLimitError.is_rate_limit("exceeding access rate")


def test_non_rate_limit_error_is_not_detected():
    assert not RateLimitError.is_rate_limit("No 09:15 candle for token 123")


def test_option_ltp_prints_only_on_change():
    assert should_print_option_ltp(None, 100.0)
    assert not should_print_option_ltp(100.0, 100.0)
    assert should_print_option_ltp(100.0, 100.05)


def test_option_contract_is_locked_from_0916_ltp_not_later_entry_ltp():
    master = [
        {"exch_seg": "NFO", "instrumenttype": "OPTSTK", "name": "LTM", "symbol": "LTM30SEP264550CE", "expiry": "30SEP2026", "strike": "455000", "token": "7", "lotsize": "100"},
        {"exch_seg": "NFO", "instrumenttype": "OPTSTK", "name": "LTM", "symbol": "LTM30SEP264550PE", "expiry": "30SEP2026", "strike": "455000", "token": "8", "lotsize": "100"},
        {"exch_seg": "NFO", "instrumenttype": "OPTSTK", "name": "LTM", "symbol": "LTM30SEP264600CE", "expiry": "30SEP2026", "strike": "460000", "token": "1", "lotsize": "100"},
        {"exch_seg": "NFO", "instrumenttype": "OPTSTK", "name": "LTM", "symbol": "LTM30SEP264600PE", "expiry": "30SEP2026", "strike": "460000", "token": "2", "lotsize": "100"},
        {"exch_seg": "NFO", "instrumenttype": "OPTSTK", "name": "LTM", "symbol": "LTM30SEP264650CE", "expiry": "30SEP2026", "strike": "465000", "token": "3", "lotsize": "100"},
        {"exch_seg": "NFO", "instrumenttype": "OPTSTK", "name": "LTM", "symbol": "LTM30SEP264650PE", "expiry": "30SEP2026", "strike": "465000", "token": "4", "lotsize": "100"},
        {"exch_seg": "NFO", "instrumenttype": "OPTSTK", "name": "LTM", "symbol": "LTM30SEP264700CE", "expiry": "30SEP2026", "strike": "470000", "token": "5", "lotsize": "100"},
        {"exch_seg": "NFO", "instrumenttype": "OPTSTK", "name": "LTM", "symbol": "LTM30SEP264700PE", "expiry": "30SEP2026", "strike": "470000", "token": "6", "lotsize": "100"},
    ]
    locked = lock_option_contract(master, "LTM", 4563.70, date(2026, 8, 28))
    later = lock_option_contract(master, "LTM", 4676.40, date(2026, 8, 28))

    assert locked["atm"] == 4600.0
    assert locked["strike"] == 4550.0
    assert locked["ce"]["symbol"] == "LTM30SEP264550CE"
    assert later["atm"] == 4650.0
    assert later["strike"] == 4600.0
    assert locked["strike"] != later["strike"]
