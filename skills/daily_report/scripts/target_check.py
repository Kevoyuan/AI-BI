"""
Target Check — Compare actual daily metrics against weekday-specific targets.
"""
import pandas as pd
from datetime import datetime


WEEKDAY_TARGETS = {
    "Monday":    {"revenue": 8000,  "tc": 200, "card": 2000, "cash": 7000},
    "Tuesday":   {"revenue": 8000,  "tc": 200, "card": 2000, "cash": 7000},
    "Wednesday": {"revenue": 8000,  "tc": 200, "card": 2000, "cash": 7000},
    "Thursday":  {"revenue": 8000,  "tc": 200, "card": 2000, "cash": 7000},
    "Friday":    {"revenue": 10000, "tc": 250, "card": 3000, "cash": 9000},
    "Saturday":  {"revenue": 15000, "tc": 380, "card": 4000, "cash": 14000},
    "Sunday":    {"revenue": 18000, "tc": 450, "card": 4000, "cash": 17000},
}


def check_target(daily_summary_df: pd.DataFrame, date: str = None) -> dict:
    """
    Compare actual vs target for a given date.

    Args:
        daily_summary_df: Output of calculate_daily_summary().
        date: Target date string (YYYY-MM-DD). If None, uses the latest day.

    Returns:
        dict with revenue, target, achievement_rate, tc, target_tc, tc_rate
    """
    df = daily_summary_df.copy()
    if date:
        row = df[df["date"].str.startswith(date)]
    else:
        row = df.tail(1)

    if row.empty:
        return {"error": "No data for the specified date."}

    date_str = str(row.iloc[0]["date"])

    # Determine weekday from date string
    try:
        dt = pd.to_datetime(date_str)
        weekday_name = dt.strftime("%A")
    except Exception:
        weekday_name = "Monday"

    target = WEEKDAY_TARGETS.get(weekday_name, WEEKDAY_TARGETS["Monday"])

    revenue = float(row.iloc[0].get("amount", 0))
    tc = int(row.iloc[0].get("orders", 0))

    return {
        "date": date_str,
        "weekday": weekday_name,
        "revenue": revenue,
        "target_revenue": target["revenue"],
        "achievement_rate": f'{revenue / target["revenue"] * 100:.1f}%',
        "tc": tc,
        "target_tc": target["tc"],
        "tc_achievement": f'{tc / target["tc"] * 100:.1f}%',
        "deviation": f'{(revenue / target["revenue"] - 1) * 100:+.1f}%',
    }
