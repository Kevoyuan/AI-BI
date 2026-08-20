"""
销售图表 — 日趋势、月趋势、支付分布
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


CHART_COLORS = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#4ECDC4', '#556270']

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


def daily_sales_trend(sales_detail_df, title="销售趋势", days=7):
    """日销售趋势折线图"""
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])

    start = datetime.now().date() - timedelta(days=days - 1)
    filtered = df[df['日期'].dt.date >= start]
    if filtered.empty:
        return None

    daily = filtered.groupby(filtered['日期'].dt.date)['实收金额'].sum().reset_index()
    daily.columns = ['日期', '销售额']

    fig = px.line(daily, x='日期', y='销售额', title=title, markers=True)
    return {"figure": _style(fig)}


def monthly_sales_trend(sales_detail_df, title="月度销售趋势"):
    """月度销售趋势柱状图"""
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])

    monthly = df.groupby(df['日期'].dt.to_period('M'))['实收金额'].sum().reset_index()
    monthly['日期'] = monthly['日期'].dt.to_timestamp()
    monthly['销售额(万)'] = monthly['实收金额'] / 10000

    fig = px.bar(monthly, x='日期', y='销售额(万)',
                 title=title, text_auto='.2f')
    fig.update_traces(textposition='outside')
    return {"figure": _style(fig)}


def payment_breakdown(sales_detail_df, title="支付方式分布"):
    """支付方式分布图"""
    df = sales_detail_df.copy()
    payments = {
        '银豹付(微信/支付宝)': df['银豹付支付'].sum(),
        '储值卡': df['储值卡支付'].sum(),
        '现金': df['现金支付'].sum(),
    }
    payment_df = pd.DataFrame(payments.items(), columns=['支付方式', '金额'])
    payment_df = payment_df[payment_df['金额'] > 0]

    fig = px.pie(payment_df, values='金额', names='支付方式',
                 title=title, hole=0.4)
    return {"figure": _style(fig)}
