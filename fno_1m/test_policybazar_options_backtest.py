from datetime import datetime, timedelta

import pandas as pd

from backtest_policybazar_options import option_driven_exit, first_option_entry, stock_exit


def bars(rows):
    return pd.DataFrame(rows, columns=["datetime","open","high","low","close","volume"]).assign(datetime=lambda x: pd.to_datetime(x.datetime))


def test_option_entry_uses_next_candle_open():
    t=pd.Timestamp("2026-08-25 09:20",tz="Asia/Kolkata")
    opt=bars([
        ["2026-08-25 09:20+05:30",10,11,9,10.5,1],
        ["2026-08-25 09:25+05:30",10.5,12,10,11.5,1],
    ])
    dt,price=first_option_entry(opt,t)
    assert dt == pd.Timestamp("2026-08-25 09:25+05:30")
    assert price == 10.5


def test_stock_long_hits_target_before_sl():
    signal=pd.Timestamp("2026-08-25 09:20+05:30")
    stock=bars([
        ["2026-08-25 09:20+05:30",100,101,99,100,1],
        ["2026-08-25 09:25+05:30",100,103,100,102,1],
    ])
    dt,price,reason=stock_exit(stock,signal,"LONG",100,99,102)
    assert price==102 and reason=="STOCK_1R"


def test_option_driven_50_percent_stop_is_one_risk_unit():
    entry_dt=pd.Timestamp("2026-08-25 09:25+05:30")
    opt=bars([
        ["2026-08-25 09:25+05:30",10,10.5,9.9,10.2,1],
        ["2026-08-25 09:30+05:30",10.2,15.2,10.0,14.5,1],
    ])
    dt,price,reason=option_driven_exit(opt,entry_dt,10.0,50.0)
    assert price==15.0 and reason=="OPTION_1R"
