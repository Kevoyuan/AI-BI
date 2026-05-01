"""
Startup Cost Analysis — investment breakdown, charts, and ROI metrics.

Features:
  - Expenditure detail table
  - Category/sub-category breakdowns (pie charts, bar charts)
  - Cumulative spending timeline
  - Summary KPI cards
"""

import streamlit as st
import pandas as pd
import altair as alt
import plotly.express as px
import sqlite3
import os
from datetime import datetime

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="📊 Startup Cost Analysis", layout="wide")

selected_date = st.date_input("Select Date", value=datetime.now().date())
selected_year_month = selected_date.strftime("%Y%m")


def _get_conn():
    db_dir = "./database"
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, f"sales_data_{selected_year_month}.db")
    return sqlite3.connect(db_path)


def load_opening_cost():
    """Load startup cost data from the database or fallback Excel."""
    try:
        conn = _get_conn()
        df = pd.read_sql("SELECT * FROM opening_cost", conn)
        conn.close()
        return df
    except Exception as e:
        st.warning(f"Database load failed: {e}")
        excel_path = os.path.join("./database", "opening_cost.xlsx")
        if os.path.exists(excel_path):
            return pd.read_excel(excel_path)
        return pd.DataFrame()


df = load_opening_cost()

if df.empty:
    st.error("No startup cost data found. Please add an `opening_cost` table or Excel file.")
    st.stop()

# ── Standardise columns ──────────────────────────────────────────────────────

# Expected: date, item, voucher, amount, phase, category
expected = ["date", "item", "voucher", "amount", "phase", "category"]
if len(df.columns) >= len(expected):
    df.columns = expected[: len(df.columns)]
elif "amount" not in df.columns:
    num_cols = df.select_dtypes(include="number").columns
    if len(num_cols) > 0:
        df = df.rename(columns={num_cols[0]: "amount"})

df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
if "date" in df.columns:
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

# ── Main title ────────────────────────────────────────────────────────────────

st.title("📊 Startup Cost Analysis Dashboard")

# ── 1. Expenditure detail ────────────────────────────────────────────────────

st.header("1. Expenditure Details")
st.dataframe(df.style.format({"amount": "{:,.2f}"}))

# ── 2. Category summary ─────────────────────────────────────────────────────

st.header("2. Category Summary")

if "category" in df.columns:
    category_data = df.groupby("category")["amount"].sum().reset_index()
    category_data = category_data.sort_values("amount", ascending=False)

    fig_cat = px.pie(
        category_data, values="amount", names="category",
        hole=0.45, title="Spending by Category",
        template="plotly_dark",
    )
    fig_cat.update_traces(textposition="outside", textinfo="label+percent+value")
    st.plotly_chart(fig_cat, use_container_width=True)

# Sub-category bar chart
if "category" in df.columns and "item" in df.columns:
    grouped = df.groupby(["category", "item"])["amount"].sum().reset_index()

    bar = alt.Chart(grouped).mark_bar().encode(
        x=alt.X("amount:Q", axis=alt.Axis(format=",.0f")),
        y=alt.Y("item:N", sort="-x"),
        color="category",
        tooltip=["category", "item", alt.Tooltip("amount", format=",.2f")],
    )
    text = bar.mark_text(align="left", baseline="middle", dx=5).encode(
        text=alt.Text("amount:Q", format=",.0f"),
    )
    st.altair_chart((bar + text).interactive(), use_container_width=True)

# ── 3. Spending timeline ─────────────────────────────────────────────────────

st.header("3. Cumulative Spending Timeline")

if "date" in df.columns:
    df_sorted = df.sort_values("date")
    df_sorted["cumulative"] = df_sorted["amount"].cumsum()

    fig_line = px.line(
        df_sorted, x="date", y="cumulative",
        title="Cumulative Investment Over Time",
        template="plotly_dark",
    )
    fig_line.update_traces(mode="lines+markers")
    st.plotly_chart(fig_line, use_container_width=True)

# ── 4. Summary metrics ──────────────────────────────────────────────────────

st.header("4. Investment Summary")

total = df["amount"].sum()
st.metric("Total Startup Investment", f"${total:,.2f}")

if "item" in df.columns:
    # Exclude initial inventory batch for adjusted total
    df_ex = df[~df["item"].str.contains("initial_inventory|first_batch", case=False, na=False)]
    total_ex = df_ex["amount"].sum()
    st.metric("Excluding Initial Inventory", f"${total_ex:,.2f}")

st.divider()
st.caption("Data source: opening_cost table / opening_cost.xlsx")
