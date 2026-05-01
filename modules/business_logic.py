"""
Business Logic Module
Core business analysis functions: waste analysis, membership stats,
high-value order detection, and payment breakdown.

All domain terminology has been generalised (no proprietary names).
"""
import streamlit as st
import pandas as pd


# ── Financial parameter extraction ───────────────────────────────────────────

def get_financial_parameters(df_financial: pd.DataFrame) -> dict:
    """Extract financial KPI parameters from the financial table."""
    if not df_financial.empty:
        return {
            "fixed_cost":    df_financial["fixed_cost"].iloc[-1],
            "cogs_ratio":    df_financial["cogs_ratio"].iloc[0],
            "op_cost_ratio": df_financial["op_cost_ratio"].iloc[0],
        }
    return {"fixed_cost": 0.0, "cogs_ratio": 0.35, "op_cost_ratio": 0.12}


# ── Sales trend helper ────────────────────────────────────────────────────────

def perform_sales_analysis(filtered_sales: pd.DataFrame,
                            merged_qty: pd.DataFrame,
                            start_date, end_date) -> None:
    """Render per-product sales trend analysis when a date range is selected."""
    if start_date == end_date:
        return

    from modules.analysis import analyze_trend

    results = []
    for product in merged_qty["product"].unique():
        rank_df = (
            filtered_sales[filtered_sales["product"] == product]
            .groupby(filtered_sales["sale_time"].dt.date)["qty"]
            .sum()
            .reset_index()
        )
        rank_df["sale_time"] = rank_df["sale_time"].apply(lambda d: d.strftime("%Y-%m-%d"))
        r = analyze_trend(rank_df, product)
        if r:
            results.append(r)

    if results:
        st.divider()
        st.subheader("📈 Product Sales Trend Analysis")
        st.dataframe(pd.DataFrame(results))


# ── High-value order analysis ─────────────────────────────────────────────────

def analyze_high_value_orders(filtered_sales: pd.DataFrame,
                               threshold: float = 50.0) -> None:
    """Display orders above a given monetary threshold."""
    st.subheader(f"💎 High-Value Orders (> ${threshold:.0f})")

    order_amounts = filtered_sales.groupby("order_id")["amount"].sum()
    high_value = order_amounts[order_amounts > threshold]

    if not high_value.empty:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("High-Value Orders", f"{len(high_value):,}")
        with col2:
            st.metric("Avg Order Amount", f"${high_value.mean():.2f}")
        with col3:
            ratio = len(high_value) / len(order_amounts) * 100
            st.metric("Share of All Orders", f"{ratio:.1f}%")

        # Amount-range distribution bar chart
        from pyecharts.charts import Bar
        from pyecharts import options as opts
        from streamlit_echarts import st_pyecharts

        bins   = [threshold, 100, 150, 200, 300, float("inf")]
        labels = [f"${int(threshold)}-100", "100-150", "150-200", "200-300", "300+"]
        counts = pd.cut(high_value, bins=bins, labels=labels, right=False).value_counts()

        bar = (
            Bar()
            .add_xaxis(counts.index.tolist())
            .add_yaxis("Orders", counts.values.tolist(),
                       label_opts=opts.LabelOpts(position="top"))
            .set_global_opts(
                title_opts=opts.TitleOpts(title="High-Value Order Distribution"),
                xaxis_opts=opts.AxisOpts(name="Amount Range"),
                yaxis_opts=opts.AxisOpts(name="Order Count"),
            )
        )
        st_pyecharts(bar)
    else:
        st.info(f"No orders above ${threshold:.0f} in the selected period.")


# ── Membership total stats ────────────────────────────────────────────────────

def analyze_membership_data(member_summary: dict) -> None:
    """Display cumulative membership statistics (all-time totals)."""
    st.subheader("💳 Cumulative Membership Statistics")

    try:
        from streamlit_extras.metric_cards import style_metric_cards
        style_metric_cards()
    except Exception:
        pass

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("👥 Total Members", f"{member_summary.get('member_count', 0):,}")
    with col2:
        st.metric("💰 Card Balance", f"${member_summary.get('total_balance', 0):,.2f}")
    with col3:
        st.metric("📦 Principal Balance", f"${member_summary.get('principal', 0):,.2f}")

    st.metric("🎁 Gift Balance", f"${member_summary.get('gift_balance', 0):,.2f}")


# ── Membership period summary ─────────────────────────────────────────────────

def analyze_membership_summary(filtered_memberships: pd.DataFrame) -> None:
    """Display membership recharge & consumption stats for the selected period."""
    st.subheader("💳 Membership Card Summary")

    if filtered_memberships.empty:
        st.info("No membership data in the selected date range.")
        return

    summary = (
        filtered_memberships
        .groupby(filtered_memberships["date"].dt.date)
        .agg({
            "recharge_amt":  "sum",
            "consumed_amt":  "sum",
            "principal_amt": "sum",
            "gift_amt":      "sum",
        })
        .reset_index()
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🔄 Total Recharge",    f"${summary['recharge_amt'].sum():,.2f}")
    with col2:
        st.metric("💰 Card Consumption",  f"${summary['consumed_amt'].sum():,.2f}")
    with col3:
        st.metric("💵 Principal Used",    f"${summary['principal_amt'].sum():,.2f}")
    with col4:
        st.metric("🎁 Gift Used",         f"${summary['gift_amt'].sum():,.2f}")


# ── Waste / shrinkage analysis ────────────────────────────────────────────────

def analyze_waste_summary(daily_summary: pd.DataFrame) -> None:
    """Display waste breakdown table and pie chart."""
    st.subheader("🗑️ Waste Breakdown")

    # Extract waste columns that exist in the summary
    waste_cols = ["samples", "waste_fresh", "waste_pastry", "cake_waste",
                  "biscuit_waste", "other_waste"]
    available = ["date"] + [c for c in waste_cols if c in daily_summary.columns]

    if len(available) <= 1:
        st.info("No waste data available for the selected period.")
        return

    waste_df = daily_summary[available].copy()

    # Totals row
    total_row = {"date": "Total"}
    for col in available[1:]:
        total_row[col] = waste_df[col].sum()
    waste_df = pd.concat([waste_df, pd.DataFrame([total_row])], ignore_index=True)

    currency_cols = [c for c in available if c != "date"]
    st.dataframe(
        waste_df.style.format({"date": "{}", **{c: "${:.2f}" for c in currency_cols}}),
        hide_index=True,
    )

    # Pie chart of waste composition
    totals = {c: daily_summary[c].sum() for c in currency_cols if c in daily_summary.columns}
    totals = {k: v for k, v in totals.items() if v > 0}

    if totals:
        from modules.charts import create_pie_chart_waste
        from streamlit_echarts import st_pyecharts
        pie_df = pd.DataFrame([totals])
        st_pyecharts(create_pie_chart_waste(pie_df))
    else:
        st.info("No waste recorded in the selected period.")


# ── Payment breakdown ─────────────────────────────────────────────────────────

def analyze_payment_breakdown(filtered_sales: pd.DataFrame) -> None:
    """Display top products by revenue."""
    st.subheader("💰 Revenue by Product (Top 10)")

    if filtered_sales.empty or "product" not in filtered_sales.columns:
        st.info("No sales data available.")
        return

    top_products = (
        filtered_sales.groupby("product")["amount"]
        .sum()
        .reset_index()
        .sort_values("amount", ascending=False)
        .head(10)
    )

    st.dataframe(
        top_products.style.format({"amount": "${:.2f}"}),
        hide_index=True,
    )

    from modules.charts import create_pie_chart
    from streamlit_echarts import st_pyecharts
    pie_data = top_products.rename(columns={"product": "category"})
    st_pyecharts(create_pie_chart(pie_data))
