"""
Anomaly Detection — Z-Score, IQR, consecutive decline, target deviation.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def zscore_anomalies(sales_detail_df: pd.DataFrame, sigma: float = 2.0):
    """
    Z-Score anomaly detection — flags days where revenue deviates
    more than N standard deviations from the mean.

    Returns:
        DataFrame with date, revenue, z_score, deviation_pct
    """
    df = sales_detail_df.copy()
    date_col = "sale_date" if "sale_date" in df.columns else "date"
    df[date_col] = pd.to_datetime(df[date_col])

    amount_col = "amount" if "amount" in df.columns else "revenue"
    daily = df.groupby(df[date_col].dt.date)[amount_col].sum()
    mean = daily.mean()
    std = daily.std()

    if std == 0:
        return pd.DataFrame(columns=["date", "revenue", "z_score", "deviation_pct"])

    zscore = (daily - mean) / std
    anomalies = daily[abs(zscore) > sigma]

    if anomalies.empty:
        return pd.DataFrame(columns=["date", "revenue", "z_score", "deviation_pct"])

    result = pd.DataFrame({
        "date": anomalies.index,
        "revenue": anomalies.values,
        "z_score": zscore[abs(zscore) > sigma].round(2),
        "deviation_pct": ((anomalies.values - mean) / mean * 100).round(1),
    })

    return result.sort_values("z_score")


def iqr_anomalies(sales_detail_df: pd.DataFrame):
    """
    IQR-based anomaly detection — outliers outside Q1-1.5*IQR or Q3+1.5*IQR.

    Returns:
        DataFrame with date, revenue, anomaly_type
    """
    df = sales_detail_df.copy()
    date_col = "sale_date" if "sale_date" in df.columns else "date"
    df[date_col] = pd.to_datetime(df[date_col])

    amount_col = "amount" if "amount" in df.columns else "revenue"
    daily = df.groupby(df[date_col].dt.date)[amount_col].sum()

    q1 = daily.quantile(0.25)
    q3 = daily.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    results = []
    for date, val in daily[daily < lower].items():
        results.append({"date": date, "revenue": val, "anomaly_type": "low_outlier"})
    for date, val in daily[daily > upper].items():
        results.append({"date": date, "revenue": val, "anomaly_type": "high_outlier"})

    return pd.DataFrame(results)


def consecutive_decline(sales_detail_df: pd.DataFrame) -> dict:
    """
    Detect consecutive revenue decline streaks.

    Returns:
        dict with current_streak, max_streak, alert_level, history
    """
    df = sales_detail_df.copy()
    date_col = "sale_date" if "sale_date" in df.columns else "date"
    df[date_col] = pd.to_datetime(df[date_col])

    amount_col = "amount" if "amount" in df.columns else "revenue"
    daily = df.groupby(df[date_col].dt.date)[amount_col].sum()

    consecutive = 0
    max_consecutive = 0
    current_start = None
    streaks = []

    for i in range(1, len(daily)):
        if daily.iloc[i] < daily.iloc[i - 1]:
            if consecutive == 0:
                current_start = daily.index[i - 1]
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            if consecutive > 0:
                streaks.append({
                    "start": str(current_start),
                    "end": str(daily.index[i - 1]),
                    "days": consecutive,
                })
            consecutive = 0

    # Still declining
    if consecutive > 0:
        streaks.append({
            "start": str(current_start),
            "end": str(daily.index[-1]),
            "days": consecutive,
        })

    level = "🔴 critical" if consecutive >= 5 else ("🟡 warning" if consecutive >= 3 else "🟢 normal")

    return {
        "current_streak": consecutive,
        "max_streak": max_consecutive,
        "alert_level": level,
        "history": streaks[-5:],
    }


def target_deviation_check(
    daily_revenue: float,
    weekday: str,
    targets: dict,
) -> dict:
    """
    Check how much the actual revenue deviates from the weekday target.

    Args:
        daily_revenue: Actual revenue for the day.
        weekday: Weekday name (e.g. "Monday").
        targets: WEEKDAY_TARGETS dict.

    Returns:
        dict with actual, target, deviation_pct, alert_level
    """
    target = targets.get(weekday, {}).get("revenue", 10000)
    deviation = (daily_revenue / target - 1) * 100 if target > 0 else 0

    if deviation < -20:
        level = "🔴 critical"
    elif deviation < -10:
        level = "🟠 warning"
    elif deviation < 0:
        level = "🟡 slightly_below"
    elif deviation > 20:
        level = "🟢 exceeding"
    else:
        level = "🟢 normal"

    return {
        "actual": daily_revenue,
        "target": target,
        "deviation_pct": round(deviation, 1),
        "alert_level": level,
    }
