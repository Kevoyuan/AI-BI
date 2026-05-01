"""
Data Loader Module
Handles reading from monthly SQLite databases and assembling
cross-month DataFrames for the dashboard.

Database convention:
  ./database/sales_data_YYYYMM.db   — one file per month
  Each file contains tables: sales, sales_detail, waste, memberships,
                              mem_detail, weather, financial
"""
import os
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from typing import Optional

from modules.config import TABLE_CONFIGS, config


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_db_path(month: str) -> str:
    return os.path.join(config.DATA_DIR, f"sales_data_{month}.db")


def _get_available_months() -> list[str]:
    """Return sorted list of available YYYYMM month strings."""
    db_dir = config.DATA_DIR
    if not os.path.exists(db_dir):
        return []
    files = [
        f for f in os.listdir(db_dir)
        if f.startswith("sales_data_") and f.endswith(".db")
    ]
    return sorted(f.replace("sales_data_", "").replace(".db", "") for f in files)


def get_available_months() -> list[str]:
    """Public accessor — used by the AI page and sidebar."""
    return _get_available_months()


def _clean_dataframe(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """
    Shared cleaning pipeline:
      1. Remove duplicates
      2. Filter future-dated rows
      3. Remove extreme outliers in amount columns
    """
    if df.empty:
        return df

    df = df.drop_duplicates()

    # Determine time column for this table
    cfg = TABLE_CONFIGS.get(table)
    time_col = cfg.time_field if cfg else None
    if time_col and time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        df = df[df[time_col] <= pd.Timestamp.now()]

    # Drop extreme amount outliers (threshold: ±1 000 000)
    amount_col_map = {
        "sales":        ["amount", "list_price"],
        "waste":        ["waste_amount"],
        "memberships":  ["recharge_amt", "consumed_amt"],
    }
    for col in amount_col_map.get(table, []):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df[df[col].abs() < 1_000_000]

    return df


def _load_table(month: str, table: str,
                parse_dates: Optional[list] = None) -> pd.DataFrame:
    """
    Generic monthly table loader with error handling.
    Returns an empty DataFrame on any failure.
    """
    path = _get_db_path(month)
    if not os.path.exists(path):
        return pd.DataFrame()

    try:
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
                (table,),
            )
            if cursor.fetchone() is None:
                return pd.DataFrame()

            df = pd.read_sql_query(
                f"SELECT * FROM {table}", conn, parse_dates=parse_dates
            )
            return _clean_dataframe(df, table)
    except Exception as exc:
        print(f"[data_loader] Failed to load {table} for {month}: {exc}")
        return pd.DataFrame()


# ── Per-table monthly loaders ─────────────────────────────────────────────────

def load_sales_for_month(month: str) -> pd.DataFrame:
    return _load_table(month, "sales", parse_dates=["sale_time"])


def load_sales_detail_for_month(month: str) -> pd.DataFrame:
    return _load_table(month, "sales_detail", parse_dates=["sale_date"])


def load_waste_for_month(month: str) -> pd.DataFrame:
    df = _load_table(month, "waste", parse_dates=["audit_time"])
    if not df.empty and "adj_date" in df.columns:
        df["adj_date"] = pd.to_datetime(df["adj_date"]).dt.date
    return df


def load_memberships_for_month(month: str) -> pd.DataFrame:
    """
    Tries 'memberships' and 'mem_detail' tables in that order,
    normalising to a common schema.
    """
    path = _get_db_path(month)
    if not os.path.exists(path):
        return pd.DataFrame()

    try:
        with sqlite3.connect(path) as conn:
            available = pd.read_sql_query(
                "SELECT name FROM sqlite_master WHERE type='table';", conn
            )["name"].tolist()

            for tbl, date_col in [("memberships", "date"), ("mem_detail", "recharge_time")]:
                if tbl in available:
                    df = pd.read_sql_query(
                        f"SELECT * FROM {tbl}", conn, parse_dates=[date_col]
                    )
                    if date_col != "date":
                        df = df.rename(columns={date_col: "date"})
                    return _clean_dataframe(df, "memberships")
    except Exception as exc:
        print(f"[data_loader] Failed to load memberships for {month}: {exc}")

    return pd.DataFrame()


def load_generic_for_month(table: str, month: str) -> pd.DataFrame:
    cfg = TABLE_CONFIGS.get(table)
    parse_dates = [cfg.time_field] if cfg and cfg.time_field else None
    return _load_table(month, table, parse_dates=parse_dates)


# ── Cross-month aggregator ────────────────────────────────────────────────────

def query_table(table: str, time_range: dict = None) -> pd.DataFrame:
    """
    Load and concatenate a table across all available months,
    optionally filtering to a date range.

    Args:
        table:      Table name (must be in TABLE_CONFIGS).
        time_range: Optional {'start_date': date, 'end_date': date}.
    """
    months = _get_available_months()
    if not months:
        return pd.DataFrame()

    loader_map = {
        "sales":        load_sales_for_month,
        "sales_detail": load_sales_detail_for_month,
        "waste":        load_waste_for_month,
        "memberships":  load_memberships_for_month,
        "mem_detail":   load_memberships_for_month,
    }

    frames = []
    for month in months:
        loader = loader_map.get(table, lambda m: load_generic_for_month(table, m))
        df = loader(month)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Date-range filter
    if time_range:
        cfg = TABLE_CONFIGS.get(table)
        time_col = cfg.time_field if cfg else None
        start = time_range.get("start_date")
        end = time_range.get("end_date")
        if time_col and time_col in combined.columns and start and end:
            try:
                combined = combined[
                    (combined[time_col].dt.date >= pd.to_datetime(start).date()) &
                    (combined[time_col].dt.date <= pd.to_datetime(end).date())
                ]
            except Exception as exc:
                print(f"[data_loader] Date filter failed: {exc}")

    if len(combined) > config.MAX_DATA_ROWS:
        combined = combined.head(config.MAX_DATA_ROWS)

    return combined


# ── Top-level loader (used by main app) ──────────────────────────────────────

def load_data():
    """
    Load all required data across available months.
    Returns (df_sales, df_waste, df_memberships, df_financial, df_weather).
    """
    months = _get_available_months()
    if not months:
        st.error("No database files found. Run the data import script first.")
        empty = pd.DataFrame()
        return empty, empty, empty, empty, empty

    sales_frames, waste_frames, membership_frames = [], [], []

    for month in months:
        s = load_sales_for_month(month)
        w = load_waste_for_month(month)
        m = load_memberships_for_month(month)

        if not s.empty:
            sales_frames.append(s)
        else:
            st.warning(f"⚠️ No sales data for {month}")

        if not w.empty:
            waste_frames.append(w)

        if not m.empty:
            membership_frames.append(m)

    df_sales       = pd.concat(sales_frames,      ignore_index=True) if sales_frames else pd.DataFrame()
    df_waste       = pd.concat(waste_frames,       ignore_index=True) if waste_frames else pd.DataFrame()
    df_memberships = pd.concat(membership_frames,  ignore_index=True) if membership_frames else pd.DataFrame()

    # Financial parameters (single record, stored in the most recent DB)
    try:
        from modules.database import load_financial_data, load_weather_data
        df_financial = load_financial_data()
        df_weather   = load_weather_data()
    except Exception as exc:
        st.warning(f"Could not load financial/weather data: {exc}")
        df_financial = pd.DataFrame()
        df_weather   = pd.DataFrame()

    return df_sales, df_waste, df_memberships, df_financial, df_weather


@st.cache_data(ttl=3600)
def load_cached_data():
    """Cache-wrapped version of load_data for the main dashboard."""
    return load_data()


# ── Post-processing helpers ───────────────────────────────────────────────────

def process_weather_data(df_weather: pd.DataFrame) -> pd.DataFrame:
    if df_weather.empty:
        return pd.DataFrame(columns=["date", "condition"])
    df = df_weather[["date", "condition"]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def get_financial_parameters(df_financial: pd.DataFrame) -> dict:
    if not df_financial.empty:
        return {
            "fixed_cost":     df_financial["fixed_cost"].iloc[-1],
            "cogs_ratio":     df_financial["cogs_ratio"].iloc[0],
            "op_cost_ratio":  df_financial["op_cost_ratio"].iloc[0],
        }
    # Safe defaults if financial data is missing
    return {"fixed_cost": 0.0, "cogs_ratio": 0.35, "op_cost_ratio": 0.12}


def load_member_summary() -> dict:
    """Load membership totals from the database module."""
    try:
        from modules.database import load_member_totals
        data = load_member_totals()
        return {
            "member_count":    data["member_count"],
            "total_balance":   data["total_balance"],
            "principal":       data["principal"],
            "gift_balance":    data["gift_balance"],
        }
    except Exception:
        return {"member_count": 0, "total_balance": 0.0, "principal": 0.0, "gift_balance": 0.0}


def load_daily_summary(start_date=None, end_date=None) -> pd.DataFrame:
    """
    Convenience function: load raw data and compute daily_summary,
    optionally filtered to a date range.
    """
    from modules.analysis import calculate_daily_summary
    from modules.date_utils import filter_data_by_date_range

    df_sales, df_waste, df_memberships, df_financial, df_weather = load_data()
    if df_sales.empty:
        return pd.DataFrame()

    df_weather = process_weather_data(df_weather)
    financial_params = get_financial_parameters(df_financial)

    if start_date and end_date:
        df_sales, df_waste, df_memberships, df_weather = filter_data_by_date_range(
            df_sales, df_waste, df_memberships, df_weather, (start_date, end_date)
        )

    return calculate_daily_summary(df_sales, df_waste, df_memberships, financial_params, df_weather)
