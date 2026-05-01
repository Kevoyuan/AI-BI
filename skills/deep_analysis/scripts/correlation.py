"""
Correlation Analysis — weather–sales correlation, category impact, cross-period comparison.
"""
import pandas as pd
import numpy as np


def weather_sales_correlation(sales_detail_df: pd.DataFrame, weather_df: pd.DataFrame):
    """
    Quantify weather impact on daily revenue.

    Returns:
        DataFrame with condition, avg_revenue, days, std, median, impact_pct
    """
    df_s = sales_detail_df.copy()
    df_s["date"] = pd.to_datetime(df_s["sale_date"] if "sale_date" in df_s.columns else df_s.get("date", pd.Series())).dt.date

    df_w = weather_df.copy()
    df_w["date"] = pd.to_datetime(df_w["date"]).dt.date

    merged = df_s.merge(df_w, on="date", how="inner")
    if merged.empty:
        return None

    amount_col = "amount" if "amount" in merged.columns else "revenue"
    stats = merged.groupby("condition").agg(
        avg_revenue=(amount_col, "mean"),
        days=(amount_col, "count"),
        std=(amount_col, "std"),
        median=(amount_col, "median"),
    ).round(0).reset_index()

    # Baseline: most common condition (cloudy) or overall mean
    baseline_row = stats[stats["condition"] == "cloudy"]
    baseline = baseline_row["avg_revenue"].values[0] if len(baseline_row) > 0 else stats["avg_revenue"].mean()
    stats["impact_pct"] = ((stats["avg_revenue"] / baseline) - 1) * 100
    stats["impact_pct"] = stats["impact_pct"].round(1)

    return stats.sort_values("avg_revenue", ascending=False)


def weather_category_correlation(sales_df: pd.DataFrame, weather_df: pd.DataFrame):
    """
    Weather impact broken down by product category.

    Returns:
        DataFrame with condition, category, avg_revenue
    """
    df_s = sales_df.copy()
    df_s["sale_time"] = pd.to_datetime(df_s["sale_time"])
    df_s["date"] = df_s["sale_time"].dt.date

    df_w = weather_df.copy()
    df_w["date"] = pd.to_datetime(df_w["date"]).dt.date

    merged = df_s.merge(df_w, on="date", how="inner")
    if merged.empty:
        return None

    stats = merged.groupby(["condition", "category"])["amount"].mean().round(0).reset_index()
    stats.columns = ["condition", "category", "avg_revenue"]
    return stats


def cross_period_comparison(
    sales_detail_df: pd.DataFrame,
    period1_label: str, period1_dates: list,
    period2_label: str, period2_dates: list,
) -> dict:
    """
    Compare revenue between two time periods.

    Args:
        period1_label: e.g. "This month"
        period1_dates: list of date objects
        period2_label: e.g. "Last month"
        period2_dates: list of date objects

    Returns:
        dict with totals, daily averages, and change percentage
    """
    df = sales_detail_df.copy()
    date_col = "sale_date" if "sale_date" in df.columns else "date"
    df[date_col] = pd.to_datetime(df[date_col]).dt.date

    p1 = df[df[date_col].isin(period1_dates)]
    p2 = df[df[date_col].isin(period2_dates)]

    amount_col = "amount" if "amount" in df.columns else "revenue"
    p1_total = p1[amount_col].sum()
    p2_total = p2[amount_col].sum()
    change = (p1_total - p2_total) / p2_total * 100 if p2_total > 0 else 0

    return {
        f"{period1_label}_total": p1_total,
        f"{period2_label}_total": p2_total,
        "change_pct": round(change, 1),
        f"{period1_label}_daily_avg": p1[amount_col].mean() if not p1.empty else 0,
        f"{period2_label}_daily_avg": p2[amount_col].mean() if not p2.empty else 0,
    }
