"""
综合仪表板 — 2×2 布局：销售趋势 + 分类占比 + 报废分析 + 关键指标
"""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Dict, Optional, Any


DEFAULTS = {"template": "plotly_white", "height": 500, "title_font_size": 16,
            "font_family": "sans-serif"}


def _style(fig, height=None):
    fig.update_layout(
        template=DEFAULTS["template"],
        height=height or DEFAULTS["height"],
        title_font_size=DEFAULTS["title_font_size"],
        font=dict(family=DEFAULTS["font_family"]),
        margin=dict(l=60, r=30, t=60, b=40),
    )
    return fig


def build_dashboard(data, days=7):
    """
    业务综合仪表板 (2×2 子图)

    Args:
        data: dict with 'sales_detail', 'sales', 'loss' DataFrames
        days: 天数范围
    """
    df_detail = data.get('sales_detail', pd.DataFrame())
    df_sales = data.get('sales', pd.DataFrame())
    df_loss = data.get('loss', pd.DataFrame())

    yesterday = datetime.now().date() - timedelta(days=1)
    last_start = yesterday - timedelta(days=days - 1)

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('销售趋势', '分类占比', '报废分析', '关键指标'),
        specs=[[{"secondary_y": False}, {"type": "pie"}],
               [{"secondary_y": False}, {"type": "indicator"}]]
    )

    # 1. 销售趋势
    if not df_detail.empty and '日期' in df_detail.columns:
        df_detail['日期'] = pd.to_datetime(df_detail['日期'])
        recent = df_detail[df_detail['日期'].dt.date >= last_start]
        if not recent.empty:
            daily = recent.groupby(recent['日期'].dt.date)['实收金额'].sum().reset_index()
            fig.add_trace(
                go.Scatter(x=daily['日期'], y=daily['实收金额'],
                           mode='lines+markers', name='日销售额'),
                row=1, col=1
            )

    # 2. 分类占比
    if not df_sales.empty and '商品分类' in df_sales.columns:
        df_sales['销售时间'] = pd.to_datetime(df_sales['销售时间'])
        y_sales = df_sales[df_sales['销售时间'].dt.date == yesterday]
        if not y_sales.empty:
            cat = y_sales.groupby('商品分类')['实收金额'].sum()
            fig.add_trace(
                go.Pie(labels=cat.index, values=cat.values, name='分类占比'),
                row=1, col=2
            )

    # 3. 报废分析
    if not df_loss.empty and '调整日期' in df_loss.columns:
        recent_loss = df_loss[df_loss['调整日期'] >= last_start]
        if not recent_loss.empty:
            d_loss = recent_loss.groupby('调整日期')['报损金额'].sum()
            fig.add_trace(
                go.Bar(x=d_loss.index, y=d_loss.values, name='日报损'),
                row=2, col=1
            )

    # 4. 关键指标
    if not df_detail.empty:
        df_detail['日期'] = pd.to_datetime(df_detail['日期'])
        y_detail = df_detail[df_detail['日期'].dt.date == yesterday]
        if not y_detail.empty:
            revenue = y_detail['实收金额'].sum()
            fig.add_trace(
                go.Indicator(
                    mode="number", value=revenue,
                    title={"text": "昨日营业额"},
                    number={'suffix': "元"}
                ),
                row=2, col=2
            )

    fig.update_layout(title_text="业务综合仪表板")
    return {"figure": _style(fig, height=800)}
