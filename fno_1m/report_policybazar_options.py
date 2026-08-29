from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def max_drawdown(pnl_series: pd.Series) -> float:
    values = pd.to_numeric(pnl_series, errors="coerce").dropna()
    if values.empty:
        return 0.0
    cumulative = values.cumsum()
    peak = cumulative.cummax()
    return float((peak - cumulative).max())


def summarize(df: pd.DataFrame, pnl_col: str) -> pd.DataFrame:
    x = df[df.status == "OK"].copy()
    if x.empty:
        return pd.DataFrame()
    x["date"] = pd.to_datetime(x["date"], errors="coerce")
    x[pnl_col] = pd.to_numeric(x[pnl_col], errors="coerce")
    x = x.dropna(subset=[pnl_col]).sort_values("date")

    def row(group: pd.DataFrame) -> pd.Series:
        pnl = group[pnl_col]
        wins = int((pnl > 0).sum())
        losses = int((pnl < 0).sum())
        gross_win = float(pnl[pnl > 0].sum())
        gross_loss = float(-pnl[pnl < 0].sum())
        return pd.Series({
            "trades": len(group),
            "wins": wins,
            "losses": losses,
            "win_pct": wins / len(group) * 100,
            "gross_profit_rupees": gross_win,
            "gross_loss_rupees": gross_loss,
            "net_pnl_rupees": float(pnl.sum()),
            "avg_pnl_rupees": float(pnl.mean()),
            "profit_factor": gross_win / gross_loss if gross_loss else float("inf"),
            "max_drawdown_rupees": max_drawdown(pnl),
        })

    return (
        x.groupby(["expiry_week", "side"], dropna=False, sort=False)
        .apply(row, include_groups=False)
        .reset_index()
    )


def summarize_by_month(df: pd.DataFrame, pnl_col: str) -> pd.DataFrame:
    x = df[df.status == "OK"].copy()
    if x.empty:
        return pd.DataFrame()
    x["month"] = pd.to_datetime(x["date"], errors="coerce").dt.to_period("M").astype(str)
    x[pnl_col] = pd.to_numeric(x[pnl_col], errors="coerce")
    x = x.dropna(subset=[pnl_col])
    return _summary_grouped(x, ["month"], pnl_col)


def summarize_long_short(df: pd.DataFrame, pnl_col: str) -> pd.DataFrame:
    x = df[df.status == "OK"].copy()
    if x.empty:
        return pd.DataFrame()
    x[pnl_col] = pd.to_numeric(x[pnl_col], errors="coerce")
    x = x.dropna(subset=[pnl_col])
    return _summary_grouped(x, ["side"], pnl_col)


def _summary_grouped(df: pd.DataFrame, group_cols: list[str], pnl_col: str) -> pd.DataFrame:
    def row(group: pd.DataFrame) -> pd.Series:
        pnl = group[pnl_col]
        wins = int((pnl > 0).sum())
        losses = int((pnl < 0).sum())
        gross_win = float(pnl[pnl > 0].sum())
        gross_loss = float(-pnl[pnl < 0].sum())
        return pd.Series({
            "trades": len(group),
            "wins": wins,
            "losses": losses,
            "win_pct": wins / len(group) * 100,
            "gross_profit_rupees": gross_win,
            "gross_loss_rupees": gross_loss,
            "net_pnl_rupees": float(pnl.sum()),
            "avg_pnl_rupees": float(pnl.mean()),
            "profit_factor": gross_win / gross_loss if gross_loss else float("inf"),
            "max_drawdown_rupees": max_drawdown(pnl),
        })
    return df.groupby(group_cols, dropna=False, sort=False).apply(row, include_groups=False).reset_index()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", default="data/policybazar_options/trades.csv")
    parser.add_argument("--out", default="data/policybazar_options")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.trades)

    for col in ["stock_driven_option_pnl_rupees", "option_driven_option_pnl_rupees"]:
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = pd.to_numeric(df[col], errors="coerce")

    stock = summarize(df, "stock_driven_option_pnl_rupees")
    option = summarize(df, "option_driven_option_pnl_rupees")
    stock_month = summarize_by_month(df, "stock_driven_option_pnl_rupees")
    option_month = summarize_by_month(df, "option_driven_option_pnl_rupees")
    long_short = summarize_long_short(df, "stock_driven_option_pnl_rupees")

    stock.to_csv(out / "weekly_summary_stock_driven.csv", index=False)
    option.to_csv(out / "weekly_summary_option_driven.csv", index=False)
    stock_month.to_csv(out / "monthly_summary_stock_driven.csv", index=False)
    option_month.to_csv(out / "monthly_summary_option_driven.csv", index=False)
    long_short.to_csv(out / "long_short_summary.csv", index=False)

    quality = (
        df.groupby(["status"], dropna=False)
        .size()
        .rename("trades")
        .reset_index()
    )
    quality.to_csv(out / "data_quality.csv", index=False)

    ok = df[df.status == "OK"].copy()
    final_rows = []
    for label, col in [
        ("STOCK_DRIVEN", "stock_driven_option_pnl_rupees"),
        ("OPTION_DRIVEN", "option_driven_option_pnl_rupees"),
    ]:
        pnl = pd.to_numeric(ok.get(col, pd.Series(dtype=float)), errors="coerce").dropna()
        wins = int((pnl > 0).sum())
        gross_profit = float(pnl[pnl > 0].sum())
        gross_loss = float(-pnl[pnl < 0].sum())
        final_rows.append({
            "view": label,
            "signals": len(df),
            "ok_trades": len(pnl),
            "data_quality_failures": int((df.status != "OK").sum()),
            "wins": wins,
            "losses": int((pnl < 0).sum()),
            "win_pct": wins / len(pnl) * 100 if len(pnl) else 0.0,
            "gross_profit_rupees": gross_profit,
            "gross_loss_rupees": gross_loss,
            "net_pnl_rupees": float(pnl.sum()) if len(pnl) else 0.0,
            "avg_pnl_rupees": float(pnl.mean()) if len(pnl) else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else float("inf"),
            "max_drawdown_rupees": max_drawdown(pnl),
        })
    pd.DataFrame(final_rows).to_csv(out / "final_summary.csv", index=False)
    print("[DONE] option summaries written")


if __name__ == "__main__":
    main()
