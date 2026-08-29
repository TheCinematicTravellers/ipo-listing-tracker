import pandas as pd

from report_policybazar_options import max_drawdown, summarize


def test_max_drawdown_is_peak_to_trough_on_cumulative_pnl():
    assert max_drawdown(pd.Series([100, -150, 50])) == 150


def test_summary_separates_week_and_side():
    df = pd.DataFrame({
        "status": ["OK", "OK"],
        "expiry_week": ["WEEK_1", "WEEK_1"],
        "side": ["LONG", "SHORT"],
        "date": ["2026-08-05", "2026-08-06"],
        "stock_driven_option_pnl_rupees": [1000, -500],
    })
    out = summarize(df, "stock_driven_option_pnl_rupees")
    assert set(out["side"]) == {"LONG", "SHORT"}
    assert set(out["expiry_week"]) == {"WEEK_1"}
    assert set(out["net_pnl_rupees"]) == {1000, -500}
