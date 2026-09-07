from forward_runner import should_print_option_ltp


def test_option_ltp_first_tick_prints():
    assert should_print_option_ltp(None, 100.0)


def test_option_ltp_unchanged_does_not_print():
    assert not should_print_option_ltp(100.0, 100.0)


def test_option_ltp_changed_prints():
    assert should_print_option_ltp(100.0, 100.05)
