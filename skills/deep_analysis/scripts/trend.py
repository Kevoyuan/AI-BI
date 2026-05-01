"""
Trend Analysis Script
Computes simple linear regression slope for a time-series,
used to classify products as growing / declining / stable.
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict


def analyze_trend(
    df: pd.DataFrame,
    label: str,
    date_col: str = "sale_time",
    value_col: str = "qty",
    min_points: int = 3,
) -> Optional[Dict]:
    """
    Fit a linear trend to a time-series and classify it.

    Args:
        df:         DataFrame with date and value columns.
        label:      Name of the product / metric being analysed.
        date_col:   Date column name.
        value_col:  Numeric value column name.
        min_points: Minimum data points required.

    Returns:
        dict with keys: label, slope, trend, mean, std
        or None if insufficient data.
    """
    if df is None or df.empty or len(df) < min_points:
        return None

    if date_col not in df.columns or value_col not in df.columns:
        return None

    values = pd.to_numeric(df[value_col], errors="coerce").dropna()
    if len(values) < min_points:
        return None

    x = np.arange(len(values), dtype=float)
    y = values.values.astype(float)

    # Linear regression via numpy least-squares
    slope, intercept = np.polyfit(x, y, 1)

    mean = float(y.mean())
    std  = float(y.std())

    # Classify trend relative to mean
    if mean == 0:
        trend = "stable"
    elif slope > 0.05 * abs(mean):
        trend = "growing"
    elif slope < -0.05 * abs(mean):
        trend = "declining"
    else:
        trend = "stable"

    return {
        "label":     label,
        "slope":     round(slope, 4),
        "trend":     trend,
        "mean":      round(mean, 2),
        "std":       round(std, 2),
    }
