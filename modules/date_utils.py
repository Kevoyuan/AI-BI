"""
Date Utilities
Date range selection widgets and DataFrame filtering helpers.
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from typing import Dict, Any, Tuple


def get_date_range_options(df_sales: pd.DataFrame) -> Dict[str, Any]:
    """
    Build a dict of named date-range options from the sales DataFrame.
    Returns latest 7 days, 30 days, MTD, custom, etc.
    """
    if df_sales.empty or "sale_time" not in df_sales.columns:
        today = date.today()
        return {"min": today, "max": today}

    dates = df_sales["sale_time"].dt.date
    return {"min": dates.min(), "max": dates.max()}


def select_date_range(date_options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Render a sidebar date-range selector and return the selection.
    Returns: {start_date, end_date, date_range, selected_dates}
    """
    max_date = date_options.get("max", date.today())
    min_date = date_options.get("min", max_date - timedelta(days=365))

    presets = {
        "Yesterday":   (max_date - timedelta(days=1), max_date - timedelta(days=1)),
        "Last 7 days": (max_date - timedelta(days=6), max_date),
        "Last 30 days":(max_date - timedelta(days=29), max_date),
        "This month":  (max_date.replace(day=1), max_date),
        "Custom":      None,
    }

    with st.sidebar:
        st.subheader("📅 Date Range")
        preset = st.selectbox("Quick select", list(presets.keys()))

        if preset == "Custom" or presets[preset] is None:
            start = st.date_input("Start date", value=max_date - timedelta(days=6),
                                  min_value=min_date, max_value=max_date)
            end   = st.date_input("End date",   value=max_date,
                                  min_value=min_date, max_value=max_date)
        else:
            start, end = presets[preset]
            st.caption(f"{start} → {end}")

    selected_dates = pd.date_range(start, end).date.tolist()
    return {
        "start_date":    start,
        "end_date":      end,
        "date_range":    f"{start} → {end}",
        "selected_dates": selected_dates,
    }


def filter_data_by_date_range(
    df_sales: pd.DataFrame,
    df_waste: pd.DataFrame,
    df_memberships: pd.DataFrame,
    df_weather: pd.DataFrame,
    date_range: Tuple[date, date],
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Filter all four DataFrames to the given (start_date, end_date) range.
    Each DataFrame is filtered by its own time column.
    """
    start, end = date_range

    def _filter(df: pd.DataFrame, col: str) -> pd.DataFrame:
        if df.empty or col not in df.columns:
            return df
        try:
            return df[
                (df[col].dt.date >= start) &
                (df[col].dt.date <= end)
            ]
        except Exception:
            return df

    fs  = _filter(df_sales,       "sale_time")
    fw  = _filter(df_waste,       "adj_date" if "adj_date" in df_waste.columns else "audit_time")
    fm  = _filter(df_memberships, "date")
    fwt = _filter(df_weather,     "date")

    return fs, fw, fm, fwt
