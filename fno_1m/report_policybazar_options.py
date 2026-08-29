from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def summarize(df: pd.DataFrame, pnl_col: str) -> pd.DataFrame:
    x=df[df.status=="OK"].copy()
    if x.empty:
        return pd.DataFrame()
    def row(g):
        pnl=g[pnl_col]
        wins=(pnl>0).sum(); losses=(pnl<0).sum()
        gross_win=pnl[pnl>0].sum(); gross_loss=-pnl[pnl<0].sum()
        return pd.Series({
            "trades":len(g),"wins":wins,"losses":losses,
            "win_pct":wins/len(g)*100,"net_pnl":pnl.sum(),
            "avg_pnl":pnl.mean(),"profit_factor":gross_win/gross_loss if gross_loss else float("inf"),
        })
    return x.groupby(["expiry_week","side"],dropna=False).apply(row,include_groups=False).reset_index()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--trades",default="data/policybazar_options/trades.csv")
    p.add_argument("--out",default="data/policybazar_options")
    a=p.parse_args()
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(a.trades)
    for col in ["stock_driven_option_pnl","option_driven_option_pnl"]:
        df[col]=pd.to_numeric(df[col],errors="coerce")
    stock=summarize(df,"stock_driven_option_pnl")
    option=summarize(df,"option_driven_option_pnl")
    stock.to_csv(out/"weekly_summary_stock_driven.csv",index=False)
    option.to_csv(out/"weekly_summary_option_driven.csv",index=False)
    quality=df.groupby(["expiry_week"],dropna=False).agg(
        signals=("status","size"),ok=("status",lambda x:(x=="OK").sum()),
        missing=("status",lambda x:(x!="OK").sum())
    ).reset_index()
    quality.to_csv(out/"data_quality.csv",index=False)
    print("[DONE] weekly summaries written")

if __name__=="__main__":
    main()
