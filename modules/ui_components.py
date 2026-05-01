"""
UI Components
Reusable Streamlit UI helpers: sidebar info, loading spinner,
error messages, financial breakdown, etc.
"""
import contextlib
import streamlit as st
import pandas as pd


def create_sidebar_info() -> None:
    """Render the sidebar info panel."""
    with st.sidebar:
        st.header("ℹ️ About")
        st.markdown(
            "**AI Business Analytics Dashboard**\n\n"
            "A Streamlit + AI analytics platform with:\n"
            "- Multi-month SQLite data store\n"
            "- Modular pyecharts visualisations\n"
            "- LLM-powered Q&A (Thin Harness, Fat Skills)\n"
            "- ML profit forecasting (Prophet + SARIMA + XGBoost)\n"
        )
        st.divider()


@contextlib.contextmanager
def show_loading_spinner(message: str = "Loading…"):
    """Context manager wrapping st.spinner."""
    with st.spinner(message):
        yield


def display_error_message(message: str) -> None:
    st.error(f"❌ {message}")


def display_data_validation_info() -> None:
    st.info(
        "**Troubleshooting checklist:**\n"
        "1. Ensure the `./database/` directory contains `sales_data_YYYYMM.db` files.\n"
        "2. Run the data import script to populate the databases.\n"
        "3. Verify the `.env` file is configured and loaded.\n"
    )


def display_financial_breakdown(row: pd.Series, financial_params: dict) -> None:
    """Display a single-day financial breakdown."""
    st.subheader("💼 Financial Breakdown (single day)")

    revenue     = row.get("amount", 0)
    list_total  = row.get("list_total", 0)
    waste_total = row.get("waste_total", 0)
    cogs_ratio  = financial_params.get("cogs_ratio", 0.35)
    op_ratio    = financial_params.get("op_cost_ratio", 0.12)
    fixed_cost  = financial_params.get("fixed_cost", 0)

    cogs    = (list_total + waste_total) * cogs_ratio
    op_cost = revenue * op_ratio
    profit  = revenue - cogs - op_cost - fixed_cost
    margin  = profit / revenue * 100 if revenue > 0 else 0

    cols = st.columns(5)
    labels = ["Revenue", "COGS", "Op Cost", "Fixed Cost", "Net Profit"]
    values = [revenue, cogs, op_cost, fixed_cost, profit]
    for col, lbl, val in zip(cols, labels, values):
        with col:
            st.metric(lbl, f"${val:,.2f}")

    st.caption(f"Net profit margin: {margin:.1f}%")


def add_divider() -> None:
    st.divider()
