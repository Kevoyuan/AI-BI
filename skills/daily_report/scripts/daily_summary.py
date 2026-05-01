"""
Daily Summary Script
Computes a day-by-day summary DataFrame from the raw sales, waste,
and membership DataFrames.

Exported:
    calculate_daily_summary(df_sales, df_waste, df_memberships,
                            financial_params, df_weather) -> pd.DataFrame
"""
import pandas as pd
import numpy as np
from datetime import date
from typing import Dict


def calculate_daily_summary(
    df_sales: pd.DataFrame,
    df_waste: pd.DataFrame,
    df_memberships: pd.DataFrame,
    financial_params: Dict[str, float],
    df_weather: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate raw transaction data into a daily summary.

    Columns in the result:
        date, amount, list_total, orders, avg_check,
        net_profit, profit_margin,
        cogs, op_cost, fixed_cost,
        waste_total, samples, waste_fresh, waste_pastry,
        weather
    """
    if df_sales.empty or "sale_time" not in df_sales.columns:
        return pd.DataFrame()

    fixed_cost   = financial_params.get("fixed_cost",    1500.0)
    cogs_ratio   = financial_params.get("cogs_ratio",    0.35)
    op_ratio     = financial_params.get("op_cost_ratio", 0.12)

    # ── Sales aggregation ─────────────────────────────────────────────────────
    s = df_sales.copy()
    s["_date"] = s["sale_time"].dt.date

    daily = (
        s.groupby("_date")
        .agg(
            amount    =("amount",    "sum"),
            list_total=("list_price","sum"),
            orders    =("order_id",  "nunique"),
        )
        .reset_index()
        .rename(columns={"_date": "date"})
    )
    daily["avg_check"] = daily["amount"] / daily["orders"].replace(0, np.nan)

    # ── Waste aggregation ─────────────────────────────────────────────────────
    waste_cols = {
        "waste_fresh":  ("note", "fresh_baked"),
        "waste_pastry": ("note", "pastry|cake"),
        "samples":      ("note", "sample"),
    }

    if not df_waste.empty and "adj_date" in df_waste.columns and "waste_amount" in df_waste.columns:
        w = df_waste.copy()
        w["adj_date"] = pd.to_datetime(w["adj_date"]).dt.date
        w["note"]     = w.get("note", pd.Series()).fillna("").astype(str)

        def _waste_by_date_and_pattern(pattern: str, exclude: str = "") -> pd.Series:
            mask = w["note"].str.contains(pattern, case=False, na=False)
            if exclude:
                mask &= ~w["note"].str.contains(exclude, case=False, na=False)
            return w[mask].groupby("adj_date")["waste_amount"].sum()

        daily = daily.merge(
            _waste_by_date_and_pattern("fresh_baked", "sample")
                .rename("waste_fresh").reset_index().rename(columns={"adj_date": "date"}),
            on="date", how="left",
        )
        daily = daily.merge(
            _waste_by_date_and_pattern("pastry|cake", "sample")
                .rename("waste_pastry").reset_index().rename(columns={"adj_date": "date"}),
            on="date", how="left",
        )
        daily = daily.merge(
            _waste_by_date_and_pattern("sample")
                .rename("samples").reset_index().rename(columns={"adj_date": "date"}),
            on="date", how="left",
        )
        daily[["waste_fresh", "waste_pastry", "samples"]] = (
            daily[["waste_fresh", "waste_pastry", "samples"]].fillna(0)
        )
        daily["waste_total"] = daily["waste_fresh"] + daily["waste_pastry"]
    else:
        daily["waste_fresh"] = daily["waste_pastry"] = daily["samples"] = daily["waste_total"] = 0.0

    # ── Membership (recharge) ─────────────────────────────────────────────────
    if not df_memberships.empty and "date" in df_memberships.columns and "recharge_amt" in df_memberships.columns:
        m = df_memberships.copy()
        m["_date"] = pd.to_datetime(m["date"]).dt.date
        mem_daily = m.groupby("_date")["recharge_amt"].sum().reset_index()
        mem_daily.columns = ["date", "recharge_amt"]
        daily = daily.merge(mem_daily, on="date", how="left")
        daily["recharge_amt"] = daily["recharge_amt"].fillna(0)
    else:
        daily["recharge_amt"] = 0.0

    # ── Weather ───────────────────────────────────────────────────────────────
    if not df_weather.empty and "date" in df_weather.columns:
        wth = df_weather[["date", "condition"]].copy()
        wth["date"] = pd.to_datetime(wth["date"]).dt.date
        daily = daily.merge(wth, on="date", how="left")
        daily["condition"] = daily["condition"].fillna("unknown")
    else:
        daily["condition"] = "unknown"

    # ── Financial calculations ────────────────────────────────────────────────
    daily["cogs"]          = (daily["list_total"] + daily["waste_total"]) * cogs_ratio
    daily["op_cost"]       = daily["amount"] * op_ratio
    daily["fixed_cost"]    = fixed_cost
    daily["net_profit"]    = daily["amount"] - daily["cogs"] - daily["op_cost"] - daily["fixed_cost"]
    daily["profit_margin"] = daily["net_profit"] / daily["amount"].replace(0, np.nan)
    daily["profit_margin"] = daily["profit_margin"].fillna(0)

    # ── Sort by date ──────────────────────────────────────────────────────────
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["date"] = daily["date"].astype(str)

    return daily
