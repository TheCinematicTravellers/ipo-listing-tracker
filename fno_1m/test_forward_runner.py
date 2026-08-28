from forward_runner import RateLimitError, should_print_option_ltp


def test_rate_limit_error_is_detected():
    assert RateLimitError.is_rate_limit("Access denied because of exceeding access rate")
    assert RateLimitError.is_rate_limit("exceeding access rate")


def test_non_rate_limit_error_is_not_detected():
    assert not RateLimitError.is_rate_limit("No 09:15 candle for token 123")


def test_option_ltp_prints_only_on_change():
    assert should_print_option_ltp(None, 100.0)
    assert not should_print_option_ltp(100.0, 100.0)
    assert should_print_option_ltp(100.0, 100.05)
