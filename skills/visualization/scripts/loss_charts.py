"""
报废图表 — 报废趋势、报废原因、报废分类对比
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


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


def waste_trend(loss_df, days=7):
    """报废趋势 + 原因分析（双面板）"""
    df = loss_df.copy()
    start = datetime.now().date() - timedelta(days=days - 1)
    recent = df[df['调整日期'] >= start]
    if recent.empty:
        return None

    daily_loss = recent.groupby('调整日期')['报损金额'].sum().reset_index()

    if '报损原因' in recent.columns:
        waste_by_reason = recent.groupby('报损原因')['报损金额'].sum().sort_values(ascending=False)

        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('报损趋势', '报损原因分析'),
            specs=[[{"secondary_y": False}], [{"type": "pie"}]]
        )
        fig.add_trace(
            go.Bar(x=daily_loss['调整日期'], y=daily_loss['报损金额'], name='报损金额'),
            row=1, col=1
        )
        fig.add_trace(
            go.Pie(labels=waste_by_reason.index, values=waste_by_reason.values, name='报损原因'),
            row=2, col=1
        )
        return {"figure": _style(fig, height=800)}

    fig = px.bar(daily_loss, x='调整日期', y='报损金额', title='报损趋势')
    return {"figure": _style(fig)}


def waste_category_comparison(loss_df, days=30):
    """报废分类对比：现烤 vs 西点 vs 试吃"""
    df = loss_df.copy()
    df['备注'] = df['备注'].fillna('')
    start = datetime.now().date() - timedelta(days=days - 1)
    recent = df[df['调整日期'] >= start]

    tasting = recent[df['备注'].str.contains('试吃', na=False)]
    baking = recent[df['备注'].str.contains('现烤', na=False) & ~df['备注'].str.contains('试吃', na=False)]
    pastry = recent[df['备注'].str.contains('西点|蛋糕', na=False) & ~df['备注'].str.contains('试吃', na=False)]

    categories = ['现烤报废', '西点报废', '试吃']
    values = [baking['报损金额'].sum(), pastry['报损金额'].sum(), tasting['报损金额'].sum()]

    fig = px.bar(x=categories, y=values, title='报废分类对比',
                 labels={'x': '报废类型', 'y': '金额'})
    return {"figure": _style(fig)}


def waste_rate_gauge(waste_rate):
    """报废率仪表盘"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=waste_rate,
        delta={'reference': 5},
        title={'text': "报废率 %"},
        gauge={
            'axis': {'range': [0, 15]},
            'steps': [
                {'range': [0, 3], 'color': "lightgreen"},
                {'range': [3, 5], 'color': "yellow"},
                {'range': [5, 15], 'color': "red"}
            ],
            'threshold': {'line': {'color': "red", 'width': 2}, 'value': 5}
        }
    ))
    return {"figure": _style(fig)}
