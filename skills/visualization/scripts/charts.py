"""
Visualization skill scripts — category, sales, waste, membership, and dashboard charts.
"""
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ── Category charts ───────────────────────────────────────────────────────────

def category_revenue_pie(sales_df: pd.DataFrame) -> go.Figure:
    """Donut chart of revenue by product category."""
    if sales_df.empty:
        return go.Figure()

    cat = sales_df.groupby("category")["amount"].sum().reset_index()
    cat.columns = ["category", "revenue"]
    cat = cat.sort_values("revenue", ascending=False)

    fig = px.pie(
        cat, values="revenue", names="category",
        hole=0.45, title="Revenue by Category",
        template="plotly_dark",
    )
    fig.update_traces(textposition="outside", textinfo="label+percent")
    return fig


def category_trend_line(sales_df: pd.DataFrame) -> go.Figure:
    """Daily revenue trend per category (stacked area)."""
    if sales_df.empty:
        return go.Figure()

    df = sales_df.copy()
    df["date"] = pd.to_datetime(df["sale_time"]).dt.date
    pivot = df.groupby(["date", "category"])["amount"].sum().reset_index()

    fig = px.area(
        pivot, x="date", y="amount", color="category",
        title="Category Revenue Trend",
        template="plotly_dark",
    )
    return fig


# ── Sales charts ──────────────────────────────────────────────────────────────

def hourly_heatmap(sales_df: pd.DataFrame) -> go.Figure:
    """Revenue heatmap by hour and day-of-week."""
    if sales_df.empty:
        return go.Figure()

    df = sales_df.copy()
    df["sale_time"] = pd.to_datetime(df["sale_time"])
    df["hour"] = df["sale_time"].dt.hour
    df["weekday"] = df["sale_time"].dt.day_name()

    pivot = df.pivot_table(
        values="amount", index="hour", columns="weekday",
        aggfunc="sum", fill_value=0,
    )
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = pivot.reindex(columns=[d for d in day_order if d in pivot.columns])

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
        colorscale="Blues", showscale=True,
    ))
    fig.update_layout(
        title="Revenue Heatmap (Hour × Weekday)",
        xaxis_title="Day", yaxis_title="Hour",
        template="plotly_dark",
    )
    return fig


def top_products_bar(sales_df: pd.DataFrame, n: int = 15) -> go.Figure:
    """Horizontal bar chart of top-N products by revenue."""
    if sales_df.empty:
        return go.Figure()

    top = (
        sales_df.groupby("product")["amount"]
        .sum().nlargest(n).reset_index()
    )
    fig = px.bar(
        top, x="amount", y="product", orientation="h",
        title=f"Top {n} Products by Revenue",
        template="plotly_dark",
    )
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return fig


# ── Waste charts ──────────────────────────────────────────────────────────────

def waste_trend_chart(waste_df: pd.DataFrame) -> go.Figure:
    """Daily waste amount trend line."""
    if waste_df.empty or "adj_date" not in waste_df.columns:
        return go.Figure()

    df = waste_df.copy()
    df["adj_date"] = pd.to_datetime(df["adj_date"]).dt.date
    daily = df.groupby("adj_date")["waste_amount"].sum().reset_index()

    fig = px.line(
        daily, x="adj_date", y="waste_amount",
        title="Daily Waste Amount",
        template="plotly_dark",
    )
    fig.add_hline(
        y=daily["waste_amount"].mean(),
        line_dash="dash", line_color="red",
        annotation_text="Average",
    )
    return fig


def waste_category_pie(waste_df: pd.DataFrame) -> go.Figure:
    """Waste amount breakdown by category."""
    if waste_df.empty:
        return go.Figure()

    cat = waste_df.groupby("category")["waste_amount"].sum().reset_index()
    fig = px.pie(
        cat, values="waste_amount", names="category",
        hole=0.4, title="Waste by Category",
        template="plotly_dark",
    )
    return fig


# ── Membership charts ─────────────────────────────────────────────────────────

def recharge_trend(memberships_df: pd.DataFrame) -> go.Figure:
    """Daily membership recharge trend."""
    if memberships_df.empty or "date" not in memberships_df.columns:
        return go.Figure()

    df = memberships_df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    daily = df.groupby("date")["recharge_amt"].sum().reset_index()

    fig = px.bar(
        daily, x="date", y="recharge_amt",
        title="Daily Membership Recharge",
        template="plotly_dark",
    )
    return fig


# ── Dashboard composition ─────────────────────────────────────────────────────

def build_dashboard_figures(dfs: dict) -> dict:
    """
    Build all standard dashboard figures from the data dict.

    Returns:
        dict of {chart_name: go.Figure}
    """
    figures = {}

    sales = dfs.get("sales", pd.DataFrame())
    waste = dfs.get("waste", pd.DataFrame())
    memberships = dfs.get("memberships", pd.DataFrame())

    if not sales.empty:
        figures["category_pie"] = category_revenue_pie(sales)
        figures["category_trend"] = category_trend_line(sales)
        figures["hourly_heatmap"] = hourly_heatmap(sales)
        figures["top_products"] = top_products_bar(sales)

    if not waste.empty:
        figures["waste_trend"] = waste_trend_chart(waste)
        figures["waste_category"] = waste_category_pie(waste)

    if not memberships.empty:
        figures["recharge_trend"] = recharge_trend(memberships)

    return figures
