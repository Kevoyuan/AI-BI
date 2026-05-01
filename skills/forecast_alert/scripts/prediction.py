"""
Sales Forecast — weighted moving average, linear regression, weekday factor.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def predict_tomorrow(sales_detail_df: pd.DataFrame) -> dict:
    """
    Predict tomorrow's revenue using weighted average of last 4 same-weekday values.

    Returns:
        dict with forecast, lower_bound, upper_bound, based_on, reference_data
    """
    df = sales_detail_df.copy()
    date_col = "sale_date" if "sale_date" in df.columns else "date"
    df[date_col] = pd.to_datetime(df[date_col])
    df["weekday"] = df[date_col].dt.dayofweek

    tomorrow_dow = (datetime.now() + timedelta(days=1)).weekday()

    same_dow = df[df["weekday"] == tomorrow_dow]
    if same_dow.empty:
        return {"error": "No same-weekday historical data available."}

    amount_col = "amount" if "amount" in df.columns else "revenue"
    recent = same_dow.groupby(same_dow[date_col].dt.date)[amount_col].sum()
    recent = recent.sort_index().tail(4)

    weights = np.array([0.15, 0.20, 0.30, 0.35])  # More recent = higher weight
    n = len(recent)
    w = weights[-n:] / weights[-n:].sum()

    predicted = float(np.dot(recent.values, w))
    std = float(recent.std()) if n > 1 else 0

    return {
        "forecast": round(predicted, 0),
        "lower_bound": round(predicted - std, 0),
        "upper_bound": round(predicted + std, 0),
        "based_on": f"last {n} same-weekday values",
        "reference_data": {str(k): float(v) for k, v in recent.items()},
    }


def predict_next_week(sales_detail_df: pd.DataFrame) -> dict:
    """
    Predict next week's revenue — 8-week linear trend + recent baseline blend.

    Returns:
        dict with forecast, trend_forecast, last_week_actual, trend_direction
    """
    df = sales_detail_df.copy()
    date_col = "sale_date" if "sale_date" in df.columns else "date"
    df[date_col] = pd.to_datetime(df[date_col])

    df["week"] = df[date_col].dt.isocalendar().week.astype(int)
    df["year"] = df[date_col].dt.isocalendar().year.astype(int)

    amount_col = "amount" if "amount" in df.columns else "revenue"
    weekly = df.groupby(["year", "week"])[amount_col].sum().reset_index()
    weekly["week_seq"] = range(len(weekly))

    coefs = np.polyfit(weekly["week_seq"], weekly[amount_col], 1)
    trend_fn = np.poly1d(coefs)

    last_week_value = float(weekly[amount_col].iloc[-1])
    next_idx = len(weekly)
    predicted = float(trend_fn(next_idx))

    blended = last_week_value * 0.6 + predicted * 0.4

    return {
        "forecast": round(blended, 0),
        "trend_forecast": round(predicted, 0),
        "last_week_actual": round(last_week_value, 0),
        "trend_direction": "up" if coefs[0] > 0 else "down",
        "weekly_change": round(float(coefs[0]), 0),
    }


def predict_next_month(sales_detail_df: pd.DataFrame) -> dict:
    """
    Predict next month's revenue — linear trend over all historical months.

    Returns:
        dict with forecast, trend_direction, r_squared, confidence
    """
    df = sales_detail_df.copy()
    date_col = "sale_date" if "sale_date" in df.columns else "date"
    df[date_col] = pd.to_datetime(df[date_col])
    df["month"] = df[date_col].dt.to_period("M")

    amount_col = "amount" if "amount" in df.columns else "revenue"
    monthly = df.groupby("month")[amount_col].sum().reset_index()
    monthly["month_seq"] = range(len(monthly))

    coefs = np.polyfit(monthly["month_seq"], monthly[amount_col], 1)
    trend_fn = np.poly1d(coefs)

    predicted_vals = trend_fn(monthly["month_seq"])
    ss_res = ((monthly[amount_col] - predicted_vals) ** 2).sum()
    ss_tot = ((monthly[amount_col] - monthly[amount_col].mean()) ** 2).sum()
    r_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0

    next_idx = len(monthly)
    predicted = float(trend_fn(next_idx))

    return {
        "forecast": round(predicted, 0),
        "trend_direction": "up" if coefs[0] > 0 else "down",
        "monthly_change": round(float(coefs[0]), 0),
        "r_squared": round(r_squared, 3),
        "confidence": "high" if r_squared > 0.7 else ("medium" if r_squared > 0.4 else "low"),
    }
