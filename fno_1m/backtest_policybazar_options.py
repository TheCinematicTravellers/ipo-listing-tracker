from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def load_option(path: Path) -> pd.DataFrame:
    x=pd.read_csv(path)
    x["datetime"]=pd.to_datetime(x["datetime"])
    return x.sort_values("datetime").reset_index(drop=True)


def first_option_entry(opt: pd.DataFrame, signal_dt: pd.Timestamp) -> tuple[pd.Timestamp,float] | None:
    # 5-minute option data cannot observe the exact intrabar stock breakout.
    # Use the next option candle OPEN to avoid look-ahead.
    x=opt[opt.datetime > signal_dt]
    if x.empty:
        return None
    row=x.iloc[0]
    return row.datetime, float(row.open)


def option_price_at_or_after(opt: pd.DataFrame, dt: pd.Timestamp) -> tuple[pd.Timestamp,float] | None:
    x=opt[opt.datetime >= dt]
    if x.empty:
        return None
    row=x.iloc[0]
    return row.datetime, float(row.open)


def option_close_at(opt: pd.DataFrame, dt: pd.Timestamp) -> tuple[pd.Timestamp,float] | None:
    x=opt[opt.datetime == dt]
    if x.empty:
        x=opt[opt.datetime < dt]
        if x.empty:
            return None
        row=x.iloc[-1]
    else:
        row=x.iloc[0]
    return row.datetime, float(row.close)


def stock_exit(stock: pd.DataFrame, signal_dt: pd.Timestamp, side: str, entry: float, sl: float, target: float) -> tuple[pd.Timestamp,float,str]:
    bars=stock[stock.datetime >= signal_dt].sort_values("datetime")
    for _,b in bars.iterrows():
        if side=="LONG":
            hit_t=float(b.high)>=target; hit_s=float(b.low)<=sl
        else:
            hit_t=float(b.low)<=target; hit_s=float(b.high)>=sl
        if hit_t and hit_s:
            break
        if hit_t:
            return b.datetime,target,"STOCK_1R"
        if hit_s:
            return b.datetime,sl,"STOCK_SL"
    eod=stock[stock.datetime.dt.strftime("%H:%M")=="15:05"]
    eod=eod[eod.datetime>=signal_dt]
    if eod.empty:
        eod=bars
    if eod.empty:
        raise RuntimeError("No stock EOD bar")
    row=eod.iloc[0]
    return row.datetime,float(row.close),"STOCK_15:05"


def option_driven_exit(opt: pd.DataFrame, entry_dt: pd.Timestamp, entry: float, stop_pct: float) -> tuple[pd.Timestamp,float,str]:
    risk=entry*stop_pct/100.0
    stop=entry-risk; target=entry+risk
    bars=opt[opt.datetime>=entry_dt].sort_values("datetime")
    for _,b in bars.iterrows():
        ht=float(b.high)>=target; hs=float(b.low)<=stop
        if ht and hs:
            continue
        if ht:
            return b.datetime,target,"OPTION_1R"
        if hs:
            return b.datetime,stop,"OPTION_SL"
    eod=opt[opt.datetime.dt.strftime("%H:%M")=="15:05"]
    if eod.empty:
        eod=bars
    if eod.empty:
        raise RuntimeError("No option EOD bar")
    row=eod.iloc[0]
    return row.datetime,float(row.close),"OPTION_15:05"


def run(manifest_path: Path, stock_csv: Path, raw_root: Path, output: Path, option_stop_pct: float) -> int:
    manifest=pd.read_csv(manifest_path)
    stock=pd.read_csv(stock_csv)
    stock["datetime"]=pd.to_datetime(stock["datetime"])
    stock=stock.sort_values("datetime")
    rows=[]
    for _,m in manifest.iterrows():
        day=pd.Timestamp(m["date"]).date()
        side=str(m["side"])
        signal_dt=pd.Timestamp(f"{m['date']} {m['stock_breakout_time']}",tz="Asia/Kolkata")
        stock_day=stock[stock.datetime.dt.date==day]
        if stock_day.empty: continue
        token=str(m["ce_token"] if side=="LONG" else m["pe_token"])
        opt_path=raw_root/token/"candles.csv"
        if not opt_path.exists():
            rows.append({**m.to_dict(),"status":"MISSING_OPTION_DATA"})
            continue
        opt=load_option(opt_path)
        ent=first_option_entry(opt,signal_dt)
        if ent is None:
            rows.append({**m.to_dict(),"status":"MISSING_OPTION_ENTRY"})
            continue
        option_entry_dt,option_entry=ent
        stock_exit_dt,stock_exit_px,stock_exit_reason=stock_exit(
            stock_day,signal_dt,side,float(m["stock_entry"]),float(m["stock_sl"]),float(m["stock_target_1r"])
        )
        stock_driven=option_close_at(opt,stock_exit_dt)
        if stock_driven is None:
            rows.append({**m.to_dict(),"status":"MISSING_OPTION_STOCK_EXIT"})
            continue
        _,stock_driven_exit=stock_driven
        od_dt,od_exit,od_reason=option_driven_exit(opt,option_entry_dt,option_entry,option_stop_pct)
        rows.append({
            **m.to_dict(),"status":"OK","option_entry_dt":option_entry_dt,"option_entry":option_entry,
            "stock_exit_dt":stock_exit_dt,"stock_exit_reason":stock_exit_reason,"stock_exit_px":stock_exit_px,
            "stock_driven_option_exit":stock_driven_exit,"stock_driven_option_pnl":stock_driven_exit-option_entry,
            "option_exit_dt":od_dt,"option_exit_reason":od_reason,"option_exit":od_exit,
            "option_driven_option_pnl":od_exit-option_entry,
            "option_stop_pct":option_stop_pct,
        })
    out=pd.DataFrame(rows)
    output.parent.mkdir(parents=True,exist_ok=True)
    out.to_csv(output,index=False)
    return len(out)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",default="data/policybazar_options/manifest.csv")
    p.add_argument("--stock-csv",required=True)
    p.add_argument("--raw",default="data/policybazar_options/raw")
    p.add_argument("--output",default="data/policybazar_options/trades.csv")
    p.add_argument("--option-stop-pct",type=float,default=50.0)
    a=p.parse_args()
    print(f"[OK] option trades={run(Path(a.manifest),Path(a.stock_csv),Path(a.raw),Path(a.output),a.option_stop_pct)}")
