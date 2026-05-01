"""
Daily Operations Dashboard — interactive daily report page.

Features:
  - Date picker with auto-refresh
  - KPI metrics: revenue, orders (TC), avg ticket (AC), membership recharges
  - Weekday-based target comparison with achievement rates
  - Category revenue breakdown
  - Waste analysis (waste rate, sample rate)
  - Monthly Excel-style summary table with CSV export
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sqlite3
import os
import functools
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=f"Daily Report {datetime.now().date().strftime('%Y%m%d')}",
    page_icon="📊",
    initial_sidebar_state="expanded",
)

# ── Date selection ────────────────────────────────────────────────────────────

selected_date = st.date_input(
    "Select Date",
    value=datetime.now().date() - timedelta(days=1),
)
selected_year_month = selected_date.strftime("%Y%m")


# ── Database connection ───────────────────────────────────────────────────────

@functools.lru_cache(maxsize=8)
def _db_exists(year_month: str) -> bool:
    db_path = os.path.join("./database", f"sales_data_{year_month}.db")
    return os.path.exists(db_path)


def _get_conn():
    db_dir = "./database"
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, f"sales_data_{selected_year_month}.db")
    if not _db_exists(selected_year_month):
        st.error(f"Database not found: sales_data_{selected_year_month}.db")
        st.info("Run `python data/mock/generate_mock_data.py` to generate demo data.")
        return None
    return sqlite3.connect(db_path)


def _load(query: str, date_cols=None):
    conn = _get_conn()
    if conn is None:
        return pd.DataFrame()
    with conn:
        return pd.read_sql_query(query, conn, parse_dates=date_cols)


def _safe_load(loader_fn, name):
    try:
        return loader_fn()
    except Exception as e:
        st.error(f"Error loading {name}: {e}")
        return pd.DataFrame()


# ── Data loaders ──────────────────────────────────────────────────────────────

with st.spinner("Loading data..."):
    df_sales = _safe_load(
        lambda: _load("SELECT * FROM sales", ["sale_time"]),
        "sales",
    )
    df_waste = _safe_load(
        lambda: _load("SELECT * FROM waste", ["audit_time"]),
        "waste",
    )
    df_memberships = _safe_load(
        lambda: _load("SELECT * FROM memberships", ["date"]),
        "memberships",
    )
    df_sales_detail = _safe_load(
        lambda: _load("SELECT * FROM sales_detail", ["sale_date"]),
        "sales_detail",
    )
    df_weather = _safe_load(
        lambda: _load("SELECT * FROM weather", ["date"]),
        "weather",
    )

# ── Waste preprocessing ──────────────────────────────────────────────────────

if not df_waste.empty and "audit_time" in df_waste.columns:
    df_waste["adj_date"] = df_waste["audit_time"].apply(
        lambda x: (x - timedelta(hours=5)).date() if pd.notna(x) else None
    ).ffill()
    if "note" in df_waste.columns:
        df_waste["note"] = df_waste["note"].bfill()
    if "reason" in df_waste.columns:
        df_waste["reason"] = df_waste["reason"].bfill()

# ── Daily filters ─────────────────────────────────────────────────────────────

daily_sales = (
    df_sales[df_sales["sale_time"].dt.date == selected_date]
    if not df_sales.empty and "sale_time" in df_sales.columns
    else pd.DataFrame()
)
daily_waste = (
    df_waste[df_waste["adj_date"] == selected_date]
    if not df_waste.empty and "adj_date" in df_waste.columns
    else pd.DataFrame()
)
daily_detail = (
    df_sales_detail[df_sales_detail["sale_date"].dt.date == selected_date]
    if not df_sales_detail.empty and "sale_date" in df_sales_detail.columns
    else pd.DataFrame()
)
daily_weather = (
    df_weather[df_weather["date"].dt.date == selected_date]
    if not df_weather.empty and "date" in df_weather.columns
    else pd.DataFrame()
)

# ── KPI computation ──────────────────────────────────────────────────────────

amt_col = "amount" if "amount" in daily_detail.columns else "revenue"
daily_revenue = float(daily_detail[amt_col].sum()) if not daily_detail.empty else 0

tc = int(daily_sales["order_id"].nunique()) if not daily_sales.empty and "order_id" in daily_sales.columns else 0
ac = daily_revenue / tc if tc > 0 else 0

# Waste
waste_amt_col = "waste_amount" if "waste_amount" in daily_waste.columns else "amount"
waste_amount = float(daily_waste[waste_amt_col].sum()) if not daily_waste.empty else 0
waste_rate = waste_amount / daily_revenue if daily_revenue > 0 else 0

# Monthly cumulative
first_of_month = selected_date.replace(day=1)
monthly_revenue = float(
    df_sales_detail[df_sales_detail["sale_date"].dt.date >= first_of_month][amt_col].sum()
) if not df_sales_detail.empty else 0

# ── Weekday targets ──────────────────────────────────────────────────────────

WEEKDAY_TARGETS = {
    0: ("Mon–Thu", 8000,  200),
    1: ("Mon–Thu", 8000,  200),
    2: ("Mon–Thu", 8000,  200),
    3: ("Mon–Thu", 8000,  200),
    4: ("Friday",  10000, 250),
    5: ("Saturday", 15000, 380),
    6: ("Sunday",  18000, 450),
}

target_label, target_rev, target_tc = WEEKDAY_TARGETS[selected_date.weekday()]

# ── Display ───────────────────────────────────────────────────────────────────

col1, col2 = st.columns(2)
with col1:
    st.header(f"📅 {selected_date.strftime('%Y-%m-%d %A')}")
with col2:
    if daily_weather.empty:
        st.info("No weather data")
    else:
        st.info(daily_weather["condition"].values[0])

col1, col2 = st.columns(2)
with col1:
    st.subheader("Monthly Cumulative Revenue")
with col2:
    st.success(f"${monthly_revenue:,.2f}")

st.divider()

col1, col2 = st.columns(2)
with col1:
    st.subheader(f"Targets ({target_label})")
    st.metric("Revenue Target", f"${target_rev:,}")
    st.metric("TC Target", f"{target_tc}")

with col2:
    st.subheader("Actual Performance")
    st.metric("Revenue", f"${daily_revenue:,.2f}", delta=f"{daily_revenue / target_rev:.0%} of target")
    st.metric("TC (Orders)", f"{tc}", delta=f"{tc / target_tc:.0%} of target" if target_tc > 0 else "")
    st.metric("AC (Avg Ticket)", f"${ac:,.2f}")

st.divider()

# ── Category breakdown ────────────────────────────────────────────────────────

if not daily_sales.empty and "category" in daily_sales.columns:
    st.subheader("Category Revenue")
    cat_sales = daily_sales.groupby("category")[amt_col if amt_col in daily_sales.columns else "amount"].sum()
    for category, amount in cat_sales.items():
        st.write(f"**{category}**: ${amount:,.2f}")

st.divider()

# ── Waste section ─────────────────────────────────────────────────────────────

st.subheader("Waste & Shrinkage")
st.write(f"**Waste Amount**: ${waste_amount:,.2f}")
st.write(f"**Waste Rate**: {waste_rate:.2%}")

st.divider()

# ── Monthly summary table ────────────────────────────────────────────────────

def create_summary_table(start_date=None, end_date=None):
    """Build an Excel-style daily summary for the selected period."""
    if df_sales_detail.empty:
        return pd.DataFrame()

    all_dates = sorted(df_sales_detail["sale_date"].dropna().dt.date.unique())
    if start_date:
        all_dates = [d for d in all_dates if d >= start_date]
    if end_date:
        all_dates = [d for d in all_dates if d <= end_date]

    rows = []
    for date in all_dates:
        try:
            d_sales = df_sales[df_sales["sale_time"].dt.date == date] if not df_sales.empty else pd.DataFrame()
            d_detail = df_sales_detail[df_sales_detail["sale_date"].dt.date == date]
            d_waste = df_waste[df_waste.get("adj_date", pd.Series()) == date] if not df_waste.empty else pd.DataFrame()

            rev = float(d_detail[amt_col].sum())
            orders = int(d_sales["order_id"].nunique()) if not d_sales.empty and "order_id" in d_sales.columns else 0
            waste = float(d_waste[waste_amt_col].sum()) if not d_waste.empty else 0

            tgt_label, tgt_rev, tgt_tc = WEEKDAY_TARGETS[date.weekday()]

            rows.append({
                "Date": date,
                "Weekday": date.strftime("%A"),
                "Revenue": rev,
                "Target": tgt_rev,
                "Achievement": f"{rev / tgt_rev:.0%}" if tgt_rev > 0 else "–",
                "Orders": orders,
                "Avg Ticket": round(rev / orders, 2) if orders > 0 else 0,
                "Waste": waste,
                "Waste Rate": f"{waste / rev:.2%}" if rev > 0 else "0%",
            })
        except Exception:
            continue

    return pd.DataFrame(rows)


if not df_sales_detail.empty:
    month_options = sorted(df_sales_detail["sale_date"].dt.to_period("M").unique())
    if month_options:
        month = st.selectbox("Select Month", options=month_options)
        start = pd.to_datetime(month.start_time).date()
        end = pd.to_datetime(month.end_time).date()

        if st.button("Generate Monthly Summary"):
            summary = create_summary_table(start_date=start, end_date=end)
            if not summary.empty:
                st.dataframe(summary)
                csv = summary.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name="daily_summary.csv",
                    mime="text/csv",
                )
