"""
Weather Impact Analysis — quantify how weather conditions affect revenue.
"""
import pandas as pd
import numpy as np


def weather_impact_summary(
    sales_detail_df: pd.DataFrame,
    weather_df: pd.DataFrame,
):
    """
    Compute average revenue for each weather condition with impact coefficient.
    Baseline is the "sunny" condition (or overall mean if sunny is absent).

    Returns:
        DataFrame with condition, avg_revenue, days, std, impact_pct
    """
    df_s = sales_detail_df.copy()
    date_col = "sale_date" if "sale_date" in df_s.columns else "date"
    df_s["date"] = pd.to_datetime(df_s[date_col]).dt.date

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

    baseline_row = stats[stats["condition"] == "sunny"]
    baseline = (
        baseline_row["avg_revenue"].values[0]
        if len(baseline_row) > 0
        else stats["avg_revenue"].mean()
    )
    stats["impact_pct"] = ((stats["avg_revenue"] / baseline) - 1) * 100
    stats["impact_pct"] = stats["impact_pct"].round(1)

    return stats.sort_values("avg_revenue", ascending=False)


def weather_category_impact(sales_df: pd.DataFrame, weather_df: pd.DataFrame):
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


def severe_weather_alert(
    weather_df: pd.DataFrame,
    sales_detail_df: pd.DataFrame,
) -> dict:
    """
    Detect severe weather patterns and estimate their revenue impact.

    Returns:
        dict with severe_days, weather_types, estimated_impact, recommendation
    """
    df_w = weather_df.copy()
    df_w["date"] = pd.to_datetime(df_w["date"]).dt.date

    severe_conditions = ["heavy_rain", "storm", "typhoon"]
    severe_data = df_w[df_w["condition"].isin(severe_conditions)]

    if severe_data.empty:
        return {"alert": "No severe weather in records.", "level": "🟢 normal"}

    total_days = len(df_w)
    severe_days = len(severe_data)

    df_s = sales_detail_df.copy()
    date_col = "sale_date" if "sale_date" in df_s.columns else "date"
    df_s["date"] = pd.to_datetime(df_s[date_col]).dt.date
    merged = df_s.merge(df_w, on="date", how="inner")

    amount_col = "amount" if "amount" in merged.columns else "revenue"
    normal_avg = merged[merged["condition"] == "sunny"][amount_col].mean()
    severe_avg = merged[merged["condition"].isin(severe_conditions)][amount_col].mean()

    impact_pct = ((severe_avg / normal_avg) - 1) * 100 if normal_avg > 0 else 0

    return {
        "severe_ratio": f"{severe_days}/{total_days} ({severe_days / total_days * 100:.1f}%)",
        "weather_types": severe_data["condition"].unique().tolist(),
        "estimated_impact": f"{impact_pct:+.1f}% (vs sunny days)",
        "recommendation": (
            "Reduce production volume, notify delivery partners, prepare contingency plan."
            if impact_pct < -10
            else "Normal operations recommended."
        ),
    }
