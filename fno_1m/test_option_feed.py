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


def test_nearest_expiry_atm_and_atm_minus_1_from_angel_ladder():
    master = [
        row("RELIANCE30SEP261400CE", "RELIANCE", "30SEP2026", "140000", "CE", "1"),
        row("RELIANCE30SEP261400PE", "RELIANCE", "30SEP2026", "140000", "PE", "2"),
        row("RELIANCE27AUG261250CE", "RELIANCE", "27AUG2026", "125000", "CE", "3"),
        row("RELIANCE27AUG261250PE", "RELIANCE", "27AUG2026", "125000", "PE", "4"),
        row("RELIANCE27AUG261300CE", "RELIANCE", "27AUG2026", "130000", "CE", "5"),
        row("RELIANCE27AUG261300PE", "RELIANCE", "27AUG2026", "130000", "PE", "6"),
        row("RELIANCE27AUG261400CE", "RELIANCE", "27AUG2026", "140000", "CE", "7"),
        row("RELIANCE27AUG261400PE", "RELIANCE", "27AUG2026", "140000", "PE", "8"),
    ]
    out = find_atm_contracts(master, "RELIANCE", 1282.0, date(2026, 8, 27))
    assert out["expiry"] == "27AUG2026"
    assert out["atm"] == 1300.0
    assert out["atm_minus_1"] == 1250.0
    assert out["strike"] == 1250.0
    assert out["ce"]["token"] == "3"
    assert out["pe"]["token"] == "4"
    assert out["ce"]["strike"] == 1250.0
    assert out["ce"]["lot_size"] == 250


def test_scaled_strike_and_eq_symbol_are_supported():
    master = [
        row("POWERGRID28AUG261250CE", "POWERGRID", "28Aug2026", "125000", "CE", "10"),
        row("POWERGRID28AUG261250PE", "POWERGRID", "28Aug2026", "125000", "PE", "11"),
        row("POWERGRID28AUG261300CE", "POWERGRID", "28Aug2026", "130000", "CE", "12"),
        row("POWERGRID28AUG261300PE", "POWERGRID", "28Aug2026", "130000", "PE", "13"),
    ]
    out = find_atm_contracts(master, "POWERGRID-EQ", 1298.0, date(2026, 8, 28))
    assert out["expiry"] == "28AUG2026"
    assert out["atm"] == 1300.0
    assert out["strike"] == 1250.0
    assert out["ce"]["token"] == "10"
    assert out["pe"]["token"] == "11"


def test_atm_minus_1_does_not_assume_fixed_strike_interval():
    master = [
        row("ABC28AUG261275CE", "ABC", "28AUG2026", "127500", "CE", "20"),
        row("ABC28AUG261275PE", "ABC", "28AUG2026", "127500", "PE", "21"),
        row("ABC28AUG261310CE", "ABC", "28AUG2026", "131000", "CE", "22"),
        row("ABC28AUG261310PE", "ABC", "28AUG2026", "131000", "PE", "23"),
        row("ABC28AUG261375CE", "ABC", "28AUG2026", "137500", "CE", "24"),
        row("ABC28AUG261375PE", "ABC", "28AUG2026", "137500", "PE", "25"),
    ]
    out = find_atm_contracts(master, "ABC", 1330.0, date(2026, 8, 28))
    assert out["atm"] == 1310.0
    assert out["strike"] == 1275.0
    assert out["ce"]["symbol"] == "ABC28AUG261275CE"
    assert out["pe"]["symbol"] == "ABC28AUG261275PE"
