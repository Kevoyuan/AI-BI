"""
会员图表 — 充值趋势、会员结构
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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


def member_charge_trend(cards_detail_df, days=7):
    """会员充值趋势折线图"""
    df = cards_detail_df.copy()
    df['充值时间'] = pd.to_datetime(df['充值时间'])

    start = datetime.now().date() - timedelta(days=days - 1)
    recent = df[df['充值时间'].dt.date >= start]
    if recent.empty:
        return None

    daily = recent.groupby(recent['充值时间'].dt.date)['充值金额'].sum().reset_index()

    fig = px.line(daily, x='充值时间', y='充值金额',
                  title='会员充值趋势', markers=True)
    return {"figure": _style(fig)}


def member_card_usage(cards_df):
    """储值卡消费结构：本金 vs 赠送"""
    df = cards_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])

    total_principal = df['本金消费金额'].sum()
    total_gift = df['赠送消费金额'].sum()

    fig = px.pie(
        values=[total_principal, total_gift],
        names=['本金消费', '赠送消费'],
        title='储值卡消费结构',
        hole=0.4
    )
    return {"figure": _style(fig)}


def daily_charge_vs_consume(cards_df):
    """每日充值 vs 消费对比"""
    df = cards_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])

    daily = df.groupby(df['日期'].dt.date).agg(
        充值=('充值总金额', 'sum'),
        消费=('储值卡消费总金额', 'sum')
    ).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(x=daily['日期'], y=daily['充值'], name='充值'))
    fig.add_trace(go.Bar(x=daily['日期'], y=daily['消费'], name='消费'))
    fig.update_layout(barmode='group', title='每日充值 vs 消费')
    return {"figure": _style(fig)}
