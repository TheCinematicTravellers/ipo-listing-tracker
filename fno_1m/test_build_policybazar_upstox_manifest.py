from datetime import date

from build_policybazar_upstox_manifest import choose_contract_pair, resolve_manifest


def test_choose_contract_pair_selects_nearest_paired_strike():
    contracts = [
        {"strike_price": 1700, "instrument_type": "CE", "instrument_key": "ce1700", "lot_size": 350},
        {"strike_price": 1700, "instrument_type": "PE", "instrument_key": "pe1700", "lot_size": 350},
        {"strike_price": 1740, "instrument_type": "CE", "instrument_key": "ce1740", "lot_size": 350},
        {"strike_price": 1740, "instrument_type": "PE", "instrument_key": "pe1740", "lot_size": 350},
    ]
    pair = choose_contract_pair(contracts, 1733)
    assert pair["strike"] == 1740
    assert pair["ce"]["instrument_key"] == "ce1740"
    assert pair["pe"]["instrument_key"] == "pe1740"


def test_resolve_manifest_maps_long_to_ce_and_uses_august_2026_expiry():
    signals = [{
        "date": "2026-08-12", "side": "LONG", "stock_entry": 1733,
        "stock_breakout_time": "09:35", "weekday": "Wednesday", "body_pct": 0.40,
        "stock_sl": 1700, "stock_target_1r": 1766, "stock_range_1r": 33,
    }]
    calendar = [date(2026, 8, d) for d in range(1, 32) if date(2026, 8, d).weekday() < 5]

    def provider(expiry):
        assert expiry == date(2026, 8, 25)
        return [
            {"strike_price": 1740, "instrument_type": "CE", "instrument_key": "NSE_FO|ce|25-08-2026", "trading_symbol": "POLICYBZR 1740 CE 25 AUG 26", "lot_size": 350, "exchange_token": "1"},
            {"strike_price": 1740, "instrument_type": "PE", "instrument_key": "NSE_FO|pe|25-08-2026", "trading_symbol": "POLICYBZR 1740 PE 25 AUG 26", "lot_size": 350, "exchange_token": "2"},
        ]

    out = resolve_manifest(signals, calendar, provider)
    assert out[0]["option_instrument_key"] == "NSE_FO|ce|25-08-2026"
    assert out[0]["option_type"] == "CE"
    assert out[0]["expiry"] == "2026-08-25"
    assert out[0]["expiry_week"] == "WEEK_2"


def test_resolve_manifest_maps_short_to_pe():
    signals = [{
        "date": "2026-08-12", "side": "SHORT", "stock_entry": 1733,
        "stock_breakout_time": "09:35", "weekday": "Wednesday", "body_pct": 0.40,
        "stock_sl": 1766, "stock_target_1r": 1700, "stock_range_1r": 33,
    }]
    calendar = [date(2026, 8, d) for d in range(1, 32) if date(2026, 8, d).weekday() < 5]
    provider = lambda expiry: [
        {"strike_price": 1740, "instrument_type": "CE", "instrument_key": "ce", "trading_symbol": "POLICYBZR 1740 CE 25 AUG 26", "lot_size": 350, "exchange_token": "1"},
        {"strike_price": 1740, "instrument_type": "PE", "instrument_key": "pe", "trading_symbol": "POLICYBZR 1740 PE 25 AUG 26", "lot_size": 350, "exchange_token": "2"},
    ]
    out = resolve_manifest(signals, calendar, provider)
    assert out[0]["option_instrument_key"] == "pe"
    assert out[0]["option_type"] == "PE"
