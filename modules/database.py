"""
Database Module
Low-level SQLite read helpers for static data tables
(financial parameters, weather, member totals).
"""
import os
import sqlite3
import pandas as pd

from modules.config import config

# ── Static file loaders (CSV / Excel) ────────────────────────────────────────

def load_financial_data() -> pd.DataFrame:
    """
    Load financial parameters (fixed costs, COGS ratio, op ratio).
    Looks for financial_params.csv in the database directory.
    Falls back to defaults if not found.
    """
    csv_path = os.path.join(config.DATA_DIR, "financial_params.csv")
    if os.path.exists(csv_path):
        try:
            return pd.read_csv(csv_path)
        except Exception as exc:
            print(f"[database] Could not load financial_params.csv: {exc}")

    # Return sensible defaults so the app still runs without the file
    return pd.DataFrame([{
        "fixed_cost":    1500.0,
        "cogs_ratio":    0.35,
        "op_cost_ratio": 0.12,
    }])


def load_weather_data() -> pd.DataFrame:
    """
    Load weather records from weather.xlsx if present.
    Expected columns: date, condition
    """
    xlsx_path = os.path.join(config.DATA_DIR, "weather.xlsx")
    if os.path.exists(xlsx_path):
        try:
            df = pd.read_excel(xlsx_path, parse_dates=["date"])
            return df[["date", "condition"]].copy()
        except Exception as exc:
            print(f"[database] Could not load weather.xlsx: {exc}")

    return pd.DataFrame(columns=["date", "condition"])


def load_member_totals() -> dict:
    """
    Load all-time membership totals from member_summary.csv if present.
    Expected columns: member_count, total_balance, principal, gift_balance
    """
    csv_path = os.path.join(config.DATA_DIR, "member_summary.csv")
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            row = df.iloc[-1]
            return {
                "member_count":  int(row.get("member_count",  0)),
                "total_balance": float(row.get("total_balance", 0)),
                "principal":     float(row.get("principal",    0)),
                "gift_balance":  float(row.get("gift_balance", 0)),
            }
        except Exception as exc:
            print(f"[database] Could not load member_summary.csv: {exc}")

    return {"member_count": 0, "total_balance": 0.0, "principal": 0.0, "gift_balance": 0.0}


# ── Generic utility ───────────────────────────────────────────────────────────

def load_with_error_handling(loader_fn, label: str) -> pd.DataFrame:
    """Wrap any loader function with uniform error handling."""
    try:
        return loader_fn()
    except Exception as exc:
        print(f"[database] Failed to load {label}: {exc}")
        return pd.DataFrame()
