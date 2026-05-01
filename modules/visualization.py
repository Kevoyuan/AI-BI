"""
Visualisation Module
Streamlit chart components for the main dashboard.
All charts use pyecharts (rendered via streamlit-echarts).
"""
import streamlit as st
import pandas as pd
import numpy as np
from pyecharts.charts import Bar, Pie, Line, HeatMap
from pyecharts import options as opts
from pyecharts.commons.utils import JsCode
from streamlit_echarts import st_pyecharts

try:
    from streamlit_extras.metric_cards import style_metric_cards
    _HAS_METRIC_CARDS = True
except Exception:
    _HAS_METRIC_CARDS = False


def _style_cards():
    if _HAS_METRIC_CARDS:
        style_metric_cards()


# ── KPI cards ─────────────────────────────────────────────────────────────────

def display_summary_metrics(daily_summary: pd.DataFrame, financial_params: dict) -> None:
    """Render top-level KPI metric cards."""
    _style_cards()

    total_revenue = daily_summary["amount"].sum()
    total_orders  = daily_summary["orders"].sum()
    total_waste   = daily_summary.get("waste_total", pd.Series([0])).sum()
    avg_check     = total_revenue / total_orders if total_orders > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("💰 Total Revenue",     f"${total_revenue:,.2f}")
    with c2: st.metric("📦 Total Orders",       f"{total_orders:,.0f}")
    with c3: st.metric("💸 Avg Check (AC)",     f"${avg_check:.2f}")
    with c4: st.metric("📉 Total Waste",        f"${total_waste:,.2f}")


# ── Daily summary table ───────────────────────────────────────────────────────

def display_daily_summary_table(daily_summary: pd.DataFrame) -> None:
    """Render the daily summary table with currency / percentage formatting."""
    st.subheader("📊 Daily Summary")

    numeric_cols = daily_summary.select_dtypes(include=[np.number]).columns.tolist()
    non_currency = {"orders", "cogs_ratio", "op_cost_ratio", "profit_margin"}
    currency_cols = [c for c in numeric_cols if c not in non_currency]

    fmt: dict = {
        "date":         "{}",
        "orders":       "{:,.0f}",
        "profit_margin":":{.2%}",
        **{c: "${:.2f}" for c in currency_cols},
    }
    st.dataframe(daily_summary.style.format(fmt, na_rep="-"), hide_index=True)


# ── Profit formula explainer ──────────────────────────────────────────────────

def display_profit_formula() -> None:
    st.markdown("### 📊 Net Profit Formula")
    st.info(
        "**Net Profit** = Revenue "
        "− COGS (list price × COGS ratio) "
        "− Operating cost (revenue × op ratio) "
        "− Fixed daily cost"
    )


# ── Trend charts ──────────────────────────────────────────────────────────────

def create_sales_trend_charts(daily_summary: pd.DataFrame) -> None:
    """Line charts: revenue, order count, and waste over time."""
    from modules.charts import create_line_chart

    st.subheader("💰 Sales Trends")

    if len(daily_summary) <= 1:
        st.info("Select a date range with at least 2 days to see trend charts.")
        return

    for metric, title, label in [
        ("amount",      "Daily Revenue",      "Revenue ($)"),
        ("orders",      "Daily Order Count",  "Orders"),
        ("waste_total", "Daily Waste Amount", "Waste ($)"),
    ]:
        if metric in daily_summary.columns:
            st.subheader(title)
            st_pyecharts(create_line_chart(daily_summary, "date", metric, title, label))

    # Waste rate
    if "waste_total" in daily_summary.columns and "list_total" in daily_summary.columns:
        daily_summary = daily_summary.copy()
        daily_summary["waste_rate"] = (
            daily_summary["waste_total"] / daily_summary["list_total"].replace(0, np.nan)
        ).round(4)
        st.subheader("Waste Rate Trend")
        st_pyecharts(create_line_chart(daily_summary, "date", "waste_rate",
                                       "Daily Waste Rate", "Waste Rate"))


# ── Cumulative charts ─────────────────────────────────────────────────────────

def create_cumulative_charts(daily_summary: pd.DataFrame) -> None:
    """Cumulative KPI cards and net-profit trend."""
    from modules.charts import create_line_chart

    st.divider()
    _style_cards()

    ds = daily_summary.copy()
    ds["cum_revenue"]  = ds["amount"].cumsum()
    ds["cum_orders"]   = ds["orders"].cumsum()
    ds["cum_waste"]    = ds.get("waste_total", 0).cumsum()
    ds["cum_profit"]   = ds["net_profit"].cumsum()
    ds["cum_margin"]   = ds["cum_profit"] / ds["cum_revenue"].replace(0, np.nan) * 100

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Cumulative Revenue",  f"${ds['cum_revenue'].iloc[-1]:,.2f}")
    with c2: st.metric("Cumulative Orders",   f"{ds['cum_orders'].iloc[-1]:,.0f}")
    with c3: st.metric("Cumulative Waste",    f"${ds['cum_waste'].iloc[-1]:,.2f}")
    with c4: st.metric("Cumulative Profit",   f"${ds['cum_profit'].iloc[-1]:,.2f}")
    with c5: st.metric("Overall Margin",      f"{ds['cum_margin'].iloc[-1]:.1f}%")

    if len(ds) > 2:
        st.subheader("Cumulative Net Profit Trend")
        st_pyecharts(create_line_chart(ds, "date", "cum_profit", "Cumulative Net Profit", "Profit ($)"))


# ── Product analysis ──────────────────────────────────────────────────────────

def create_product_analysis_charts(
    filtered_sales: pd.DataFrame,
    filtered_waste: pd.DataFrame,
) -> None:
    """Stacked bar: sales vs waste quantities by product."""
    from modules.charts import create_stacked_bar_chart, create_pie_chart

    if filtered_sales.empty or "product" not in filtered_sales.columns:
        st.info("No product data available.")
        return

    sales_qty = (
        filtered_sales.groupby("product")
        .agg(qty=("qty", "sum"), amount=("amount", "sum"), category=("category", "first"))
        .reset_index()
    )

    if not filtered_waste.empty and "qty" in filtered_waste.columns:
        valid_waste = filtered_waste[
            filtered_waste["category"].str.contains(
                "fresh_baked|pastry|cake|biscuit", case=False, na=False
            )
        ].copy()
        valid_waste["product"] = valid_waste["product"].fillna(
            "Unknown (" + valid_waste["category"].astype(str) + ")"
        )
        waste_qty = (
            valid_waste[valid_waste["qty"] > 0]
            .groupby("product")["qty"].sum()
            .reset_index()
            .rename(columns={"qty": "waste_qty"})
        )
        merged = sales_qty.merge(waste_qty, on="product", how="outer").fillna(0)
    else:
        merged = sales_qty.copy()
        merged["waste_qty"] = 0

    st.subheader("📊 Sales vs Waste by Product")
    if not merged.empty:
        st_pyecharts(create_stacked_bar_chart(merged), height="1400px")

        categories = merged["category"].unique().tolist()
        selected = st.radio("Filter by category", categories, horizontal=True)
        filt = merged[merged["category"] == selected].copy()
        filt["waste_rate"] = filt["waste_qty"] / (filt["qty"] + filt["waste_qty"]).replace(0, np.nan)
        st_pyecharts(create_stacked_bar_chart(filt))
        st.dataframe(filt, hide_index=True)


# ── Hourly analysis ───────────────────────────────────────────────────────────

def create_hourly_analysis_charts(filtered_sales: pd.DataFrame) -> None:
    """24-hour order distribution bar chart."""
    st.subheader("⏰ Hourly Order Distribution")

    if filtered_sales.empty or "sale_time" not in filtered_sales.columns:
        st.info("No sales data available.")
        return

    hourly = (
        filtered_sales.groupby(filtered_sales["sale_time"].dt.hour)["order_id"]
        .nunique()
        .reindex(range(24), fill_value=0)
    )

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Avg Orders/Hour", f"{hourly.mean():.1f}")
    with c2: st.metric("Peak Hour",       f"{hourly.idxmax()}:00")
    with c3: st.metric("Peak Volume",     f"{hourly.max():.0f}")

    bar = (
        Bar()
        .add_xaxis([str(h) for h in range(24)])
        .add_yaxis("Orders", hourly.values.tolist(),
                   label_opts=opts.LabelOpts(is_show=True, position="top"))
        .set_global_opts(
            title_opts=opts.TitleOpts(title="24-Hour Order Distribution"),
            xaxis_opts=opts.AxisOpts(name="Hour"),
            yaxis_opts=opts.AxisOpts(name="Orders"),
        )
    )
    st_pyecharts(bar)

    if hourly.sum() > 0:
        morning   = hourly[9:12].sum()
        lunch     = hourly[12:15].sum()
        afternoon = hourly[15:18].sum()
        evening   = hourly[18:24].sum()
        total     = hourly[9:24].sum()
        if total > 0:
            st.markdown(
                f"- **Morning** (9–12): {morning:.0f} ({morning/total*100:.1f}%)\n"
                f"- **Lunch** (12–15): {lunch:.0f} ({lunch/total*100:.1f}%)\n"
                f"- **Afternoon** (15–18): {afternoon:.0f} ({afternoon/total*100:.1f}%)\n"
                f"- **Evening** (18–24): {evening:.0f} ({evening/total*100:.1f}%)"
            )


# ── Customer behaviour ────────────────────────────────────────────────────────

def create_customer_behavior_analysis(filtered_sales: pd.DataFrame) -> None:
    """Items-per-order distribution chart."""
    st.subheader("🛍️ Customer Purchase Behaviour")

    if filtered_sales.empty or "order_id" not in filtered_sales.columns:
        return

    items_per_order = filtered_sales.groupby("order_id")["qty"].sum()

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Avg Items/Order",    f"{items_per_order.mean():.1f}")
    with c2: st.metric("Max Items/Order",    f"{items_per_order.max():.0f}")
    with c3: st.metric("Median Items/Order", f"{items_per_order.median():.1f}")

    dist = items_per_order.value_counts().sort_index()
    bar = (
        Bar()
        .add_xaxis(dist.index.astype(str).tolist())
        .add_yaxis("Orders", dist.values.tolist(),
                   label_opts=opts.LabelOpts(is_show=True, position="top"))
        .set_global_opts(
            title_opts=opts.TitleOpts(title="Items per Order Distribution"),
            xaxis_opts=opts.AxisOpts(name="Item Count"),
            yaxis_opts=opts.AxisOpts(name="Orders"),
        )
    )
    st_pyecharts(bar)


# ── Heatmap ───────────────────────────────────────────────────────────────────

def create_heatmap_visualization(filtered_sales: pd.DataFrame) -> None:
    """Date × Hour order-count heatmap."""
    st.subheader("📈 Date × Hour Order Heatmap")

    if filtered_sales.empty or "sale_time" not in filtered_sales.columns:
        return

    counts = (
        filtered_sales.groupby(
            [filtered_sales["sale_time"].dt.date,
             filtered_sales["sale_time"].dt.hour]
        )["order_id"].nunique()
    )
    if counts.empty:
        return

    df_h = pd.DataFrame({
        "date":   [x[0] for x in counts.index],
        "hour":   [x[1] for x in counts.index],
        "orders": counts.values,
    })
    pivot = df_h.pivot(index="date", columns="hour", values="orders").fillna(0)

    dates = [d.strftime("%m-%d") for d in pivot.index]
    hours = [f"{h}h" for h in pivot.columns]
    data  = [[j, i, int(pivot.iloc[i, j])]
             for i in range(len(pivot.index))
             for j in range(len(pivot.columns))]

    hm = (
        HeatMap()
        .add_xaxis(hours)
        .add_yaxis("Orders", dates, data,
                   label_opts=opts.LabelOpts(is_show=False))
        .set_global_opts(
            title_opts=opts.TitleOpts(title="Orders by Date & Hour"),
            tooltip_opts=opts.TooltipOpts(
                formatter=JsCode(
                    "function(p){"
                    "return 'Date: '+p.value[1]+'<br>Hour: '+p.value[0]+'<br>Orders: '+p.value[2];}"
                )
            ),
            visualmap_opts=opts.VisualMapOpts(
                min_=0,
                max_=int(pivot.values.max()),
                is_calculable=True,
                orient="horizontal",
                pos_left="center",
                range_color=["#dbeafe", "#1d4ed8"],
            ),
        )
    )
    st_pyecharts(hm, height="500px")

    if st.checkbox("Show raw data table"):
        pivot.columns = [f"{h}h" for h in pivot.columns]
        st.dataframe(pivot.style.format("{:.0f}"), height=400)
