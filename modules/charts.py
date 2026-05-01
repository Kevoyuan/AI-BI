"""
Charts Module
Reusable pyecharts chart factories used across the application.
"""
import pandas as pd
from pyecharts.charts import Bar, Pie, Line
from pyecharts import options as opts


def create_line_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    y_label: str = "",
) -> Line:
    """Generic line chart."""
    x_data = [str(v) for v in df[x_col].tolist()]
    y_data = [round(float(v), 2) for v in df[y_col].tolist()]

    return (
        Line()
        .add_xaxis(x_data)
        .add_yaxis(y_label, y_data,
                   is_smooth=True,
                   label_opts=opts.LabelOpts(is_show=False))
        .set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            datazoom_opts=[opts.DataZoomOpts()],
        )
    )


def create_stacked_bar_chart(df: pd.DataFrame) -> Bar:
    """
    Stacked bar: sales qty (blue) and waste qty (red) per product.
    Expects columns: product, qty, waste_qty.
    """
    products = df["product"].tolist()
    sales    = df["qty"].tolist()
    waste    = df.get("waste_qty", pd.Series([0] * len(df))).tolist()

    return (
        Bar()
        .add_xaxis(products)
        .add_yaxis("Sales",  sales, stack="total",
                   label_opts=opts.LabelOpts(is_show=False))
        .add_yaxis("Waste",  waste, stack="total",
                   label_opts=opts.LabelOpts(is_show=False))
        .reversal_axis()
        .set_series_opts(label_opts=opts.LabelOpts(position="right"))
        .set_global_opts(
            title_opts=opts.TitleOpts(title="Sales vs Waste by Product"),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            legend_opts=opts.LegendOpts(pos_top="5%"),
        )
    )


def create_pie_chart(df: pd.DataFrame) -> Pie:
    """
    Pie chart of revenue share.
    Expects columns: category (or product), amount.
    """
    label_col = "category" if "category" in df.columns else "product"
    data = [(str(r[label_col]), float(r["amount"])) for _, r in df.iterrows()]

    return (
        Pie()
        .add("Revenue", data)
        .set_global_opts(title_opts=opts.TitleOpts(title="Revenue Share"))
        .set_series_opts(
            label_opts=opts.LabelOpts(
                formatter="{b}: {d}%",
                position="outside",
            )
        )
    )


def create_pie_chart_waste(df: pd.DataFrame) -> Pie:
    """
    Pie chart of waste composition.
    Expects a single-row DataFrame with waste-category columns as values.
    """
    if df.empty:
        return Pie().add("Waste", [])

    row = df.iloc[0]
    data = [(col, float(val)) for col, val in row.items() if float(val) > 0]

    return (
        Pie()
        .add("Waste", data)
        .set_global_opts(title_opts=opts.TitleOpts(title="Waste Composition"))
        .set_series_opts(
            label_opts=opts.LabelOpts(formatter="{b}: {d}%")
        )
    )
