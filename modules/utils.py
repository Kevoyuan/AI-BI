"""
Utility helpers.
"""
import pandas as pd


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Return numerator / denominator, or default if denominator is zero."""
    return numerator / denominator if denominator != 0 else default


def format_currency(value: float, symbol: str = "$") -> str:
    """Format a float as a currency string."""
    if abs(value) >= 1_000_000:
        return f"{symbol}{value/1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"{symbol}{value/1_000:.1f}K"
    return f"{symbol}{value:.2f}"


def coerce_date_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Coerce a column to datetime, dropping rows that fail to parse."""
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")
        df = df.dropna(subset=[col])
    return df
