"""
AI Business Analytics Dashboard
Main application entry point — modular architecture demo.
"""
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

import streamlit as st
import pandas as pd
from datetime import datetime

# Page config — must be first Streamlit call
st.set_page_config(
    page_title="Business Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Import application modules
from modules.data_loader import load_cached_data, process_weather_data, load_member_summary
from modules.date_utils import get_date_range_options, select_date_range, filter_data_by_date_range
from modules.visualization import (
    display_summary_metrics, display_daily_summary_table, display_profit_formula,
    create_sales_trend_charts, create_cumulative_charts, create_product_analysis_charts,
    create_hourly_analysis_charts, create_customer_behavior_analysis, create_heatmap_visualization
)
from modules.business_logic import (
    perform_sales_analysis, analyze_high_value_orders, analyze_membership_data,
    analyze_membership_summary, analyze_waste_summary, analyze_payment_breakdown,
    get_financial_parameters
)
from modules.ui_components import (
    display_financial_breakdown, create_sidebar_info, display_data_validation_info,
    show_loading_spinner, display_error_message, add_divider
)
from modules.analysis import calculate_daily_summary
from modules.prediction import predict_cumulative_profit
from modules.prediction_display import display_prediction_results

# ── Page Header ──────────────────────────────────────────────────────────────
st.title("📊 Business Analytics Dashboard")


@st.cache_data(ttl=3600)
def cached_load_data():
    """Cached data loader — refreshed every hour."""
    return load_cached_data()


def main():
    """Main application flow."""

    # ── Data Loading ─────────────────────────────────────────────────────────
    with show_loading_spinner("Loading data…"):
        df_sales, df_waste, df_memberships, df_financial, df_weather = cached_load_data()

    if df_sales.empty:
        display_error_message("No sales data loaded. Check your database directory.")
        display_data_validation_info()
        st.stop()

    # ── Data Preparation ─────────────────────────────────────────────────────
    df_weather = process_weather_data(df_weather)
    financial_params = get_financial_parameters(df_financial)
    member_summary = load_member_summary()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    create_sidebar_info()

    # ── Date Range Selection ──────────────────────────────────────────────────
    date_options = get_date_range_options(df_sales)
    date_selection = select_date_range(date_options)

    start_date = date_selection["start_date"]
    end_date = date_selection["end_date"]

    filtered_sales, filtered_waste, filtered_memberships, filtered_weather = (
        filter_data_by_date_range(df_sales, df_waste, df_memberships, df_weather, (start_date, end_date))
    )

    st.subheader(f"📅 Analysis Period: {start_date} → {end_date}")

    # ── Core Calculation ──────────────────────────────────────────────────────
    daily_summary = calculate_daily_summary(
        filtered_sales, filtered_waste, filtered_memberships, financial_params, filtered_weather
    )

    if daily_summary.empty:
        display_error_message("No data in selected date range.")
        return

    # ── KPI Cards ─────────────────────────────────────────────────────────────
    display_summary_metrics(daily_summary, financial_params)
    add_divider()

    # ── Daily Summary Table ───────────────────────────────────────────────────
    display_daily_summary_table(daily_summary)
    add_divider()

    # ── Profit Formula ────────────────────────────────────────────────────────
    display_profit_formula()

    if len(daily_summary) == 1:
        display_financial_breakdown(daily_summary.iloc[0], financial_params)

    add_divider()

    # ── Sales Trend Charts ────────────────────────────────────────────────────
    create_sales_trend_charts(daily_summary)

    # ── Cumulative Charts ─────────────────────────────────────────────────────
    create_cumulative_charts(daily_summary)

    # ── ML Profit Prediction ──────────────────────────────────────────────────
    if len(daily_summary) > 30:
        results = predict_cumulative_profit(daily_summary)
        display_prediction_results(results)
    else:
        st.info("At least 30 days of data is required for prediction analysis.")

    add_divider()

    # ── Product Analysis ──────────────────────────────────────────────────────
    create_product_analysis_charts(filtered_sales, filtered_waste)
    add_divider()

    # ── Payment Breakdown ─────────────────────────────────────────────────────
    analyze_payment_breakdown(filtered_sales)
    add_divider()

    # ── Waste / Loss Analysis ─────────────────────────────────────────────────
    analyze_waste_summary(daily_summary)
    add_divider()

    # ── Membership Analysis ───────────────────────────────────────────────────
    analyze_membership_summary(filtered_memberships)
    add_divider()

    analyze_membership_data(member_summary)
    add_divider()

    # ── Hourly Sales Patterns ─────────────────────────────────────────────────
    create_hourly_analysis_charts(filtered_sales)
    add_divider()

    # ── Customer Behavior ─────────────────────────────────────────────────────
    create_customer_behavior_analysis(filtered_sales)
    add_divider()

    # ── High-Value Orders ─────────────────────────────────────────────────────
    analyze_high_value_orders(filtered_sales)
    add_divider()

    # ── Heatmap ───────────────────────────────────────────────────────────────
    create_heatmap_visualization(filtered_sales)


if __name__ == "__main__":
    main()
