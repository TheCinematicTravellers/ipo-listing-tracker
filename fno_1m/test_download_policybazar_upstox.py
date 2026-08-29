import pandas as pd

from download_policybazar_upstox import cache_path, parse_candles


def test_parse_candles_preserves_ist_and_ohlcv():
    payload = {
        "status": "success",
        "data": {"candles": [["2026-08-12T09:40:00+05:30", 10, 12, 9, 11, 350, 7000]]},
    }
    out = parse_candles(payload)
    assert list(out.columns) == ["datetime", "open", "high", "low", "close", "volume", "open_interest"]
    assert str(out.iloc[0]["datetime"].tz) == "Asia/Kolkata"
    assert out.iloc[0]["open"] == 10


def test_parse_candles_returns_sorted_deduplicated_rows():
    payload = {
        "status": "success",
        "data": {"candles": [
            ["2026-08-12T09:40:00+05:30", 12, 13, 11, 12, 100, 200],
            ["2026-08-12T09:35:00+05:30", 10, 11, 9, 10, 100, 100],
            ["2026-08-12T09:35:00+05:30", 10, 11, 9, 10, 100, 100],
        ]},
    }
    out = parse_candles(payload)
    assert len(out) == 2
    assert out.iloc[0]["open"] == 10
    assert out.iloc[1]["open"] == 12


def test_cache_path_uses_expired_instrument_key(tmp_path):
    assert cache_path(tmp_path, "NSE_FO|139523|25-08-2026") == tmp_path / "NSE_FO|139523|25-08-2026" / "candles.csv"
