"""
Waste / Shrinkage Analysis — categorisation, rate trend, reason breakdown.
"""
import pandas as pd
import numpy as np


def categorize_waste(waste_df: pd.DataFrame) -> dict:
    """
    Split waste records into categories: fresh_baked, pastry, sample, other.

    Returns:
        dict of DataFrames keyed by category name
    """
    df = waste_df.copy()
    df["note"] = df.get("note", pd.Series(dtype=str)).fillna("")
    df["reason"] = df.get("reason", pd.Series(dtype=str)).fillna("")

    categories = {}

    # Samples / tastings
    mask_sample = df["note"].str.contains("sample|tasting", case=False, na=False)
    categories["sample"] = df[mask_sample]

    # Fresh-baked waste (excluding samples)
    mask_fresh = (
        df["note"].str.contains("fresh_baked", case=False, na=False)
        & ~mask_sample
    )
    categories["fresh_baked_waste"] = df[mask_fresh]

    # Pastry waste (excluding samples)
    mask_pastry = (
        df["note"].str.contains("pastry|cake", case=False, na=False)
        & ~mask_sample
    )
    categories["pastry_waste"] = df[mask_pastry]

    # Quality issues
    mask_quality = df["reason"].str.contains("quality", case=False, na=False)
    categories["quality_issue"] = df[mask_quality]

    return categories


def waste_rate_trend(waste_df: pd.DataFrame, sales_detail_df: pd.DataFrame):
    """
    Daily waste rate = non-sample waste / revenue.

    Returns:
        DataFrame with date, waste_amount, revenue, waste_rate_pct
    """
    df_w = waste_df.copy()
    df_w = df_w[~df_w.get("note", pd.Series(dtype=str)).str.contains("sample", case=False, na=False)]

    date_col = "adj_date" if "adj_date" in df_w.columns else "date"
    daily_waste = df_w.groupby(date_col)["waste_amount"].sum().reset_index()
    daily_waste.columns = ["date", "waste_amount"]

    df_s = sales_detail_df.copy()
    s_date_col = "sale_date" if "sale_date" in df_s.columns else "date"
    df_s["date"] = pd.to_datetime(df_s[s_date_col]).dt.date
    daily_sales = df_s.groupby("date")["amount"].sum().reset_index()

    daily_waste["date"] = pd.to_datetime(daily_waste["date"]).dt.date
    merged = daily_waste.merge(daily_sales, on="date", how="inner")
    merged["waste_rate_pct"] = (merged["waste_amount"] / merged["amount"] * 100).round(2)

    return merged


def waste_reason_breakdown(waste_df: pd.DataFrame):
    """
    Breakdown of waste by reason.

    Returns:
        DataFrame with reason, amount, count, share_pct
    """
    df = waste_df.copy()
    df = df[~df.get("note", pd.Series(dtype=str)).str.contains("sample", case=False, na=False)]

    reason_col = "reason" if "reason" in df.columns else "note"
    breakdown = df.groupby(reason_col).agg(
        amount=("waste_amount", "sum"),
        count=("waste_amount", "count"),
    ).reset_index().sort_values("amount", ascending=False)

    total = breakdown["amount"].sum()
    breakdown["share_pct"] = (breakdown["amount"] / total * 100).round(1) if total > 0 else 0

    return breakdown
