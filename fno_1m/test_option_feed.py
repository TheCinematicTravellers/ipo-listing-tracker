from datetime import date

from option_feed import find_atm_contracts


def row(symbol, name, expiry, strike, option_type, token, lot=250):
    return {
        "exch_seg": "NFO",
        "instrumenttype": "OPTSTK",
        "name": name,
        "symbol": symbol,
        "expiry": expiry,
        "strike": str(strike),
        "token": token,
        "lotsize": str(lot),
    }


def test_nearest_expiry_atm_ce_pe():
    master = [
        row("RELIANCE30SEP261400CE", "RELIANCE", "30SEP2026", "140000", "CE", "1"),
        row("RELIANCE30SEP261400PE", "RELIANCE", "30SEP2026", "140000", "PE", "2"),
        row("RELIANCE27AUG261300CE", "RELIANCE", "27AUG2026", "130000", "CE", "3"),
        row("RELIANCE27AUG261300PE", "RELIANCE", "27AUG2026", "130000", "PE", "4"),
    ]
    out = find_atm_contracts(master, "RELIANCE", 1282.0, date(2026, 8, 27))
    assert out["expiry"] == "27AUG2026"
    assert out["strike"] == 1300.0
    assert out["ce"]["token"] == "3"
    assert out["pe"]["token"] == "4"
    assert out["ce"]["lot_size"] == 250


def test_scaled_strike_and_eq_symbol_are_supported():
    master = [
        row("POWERGRID28AUG261300CE", "POWERGRID", "28AUG2026", "130000", "CE", "10"),
        row("POWERGRID28AUG261300PE", "POWERGRID", "28AUG2026", "130000", "PE", "11"),
    ]
    out = find_atm_contracts(master, "POWERGRID-EQ", 1298.0, date(2026, 8, 28))
    assert out["strike"] == 1300.0
