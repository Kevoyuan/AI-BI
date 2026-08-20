"""
分类图表 — 饼图、柱状图、排名、客单价
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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


def category_pie(sales_df, date=None, title="商品分类销售占比"):
    """分类销售占比环形图"""
    data = sales_df.copy()
    if date and '销售时间' in data.columns:
        data['销售时间'] = pd.to_datetime(data['销售时间'])
        data = data[data['销售时间'].dt.date == date]
    if data.empty:
        return None

    cat = data.groupby('商品分类')['实收金额'].sum().reset_index()
    cat = cat.sort_values('实收金额', ascending=False)

    fig = px.pie(cat, values='实收金额', names='商品分类',
                 title=title, hole=0.4)
    return {"figure": _style(fig)}


def category_bar(sales_df, date=None, title="各类别销售额对比"):
    """分类销售柱状图"""
    data = sales_df.copy()
    if date and '销售时间' in data.columns:
        data['销售时间'] = pd.to_datetime(data['销售时间'])
        data = data[data['销售时间'].dt.date == date]
    if data.empty:
        return None

    cat = data.groupby('商品分类')['实收金额'].sum().reset_index()
    fig = px.bar(cat, x='商品分类', y='实收金额', title=title)
    return {"figure": _style(fig)}


def top_products(sales_df, top_n=10, date=None):
    """热门商品排名水平柱状图"""
    data = sales_df.copy()
    if date and '销售时间' in data.columns:
        data['销售时间'] = pd.to_datetime(data['销售时间'])
        data = data[data['销售时间'].dt.date == date]
    if data.empty:
        return None

    top = data.groupby('商品名称')['销售数量'].sum().sort_values(ascending=False).head(top_n)

    fig = px.bar(x=top.values, y=top.index, orientation='h',
                 title=f'热门商品 Top {top_n}',
                 labels={'x': '销售数量', 'y': '商品名称'})
    fig.update_layout(yaxis={'categoryorder': 'total ascending'})
    return {"figure": _style(fig)}


def category_ac(sales_df, date=None):
    """各分类客单价分析"""
    data = sales_df.copy()
    if date and '销售时间' in data.columns:
        data['销售时间'] = pd.to_datetime(data['销售时间'])
        data = data[data['销售时间'].dt.date == date]
    if data.empty:
        return None

    cat_ac = data.groupby('商品分类').agg({
        '实收金额': 'sum',
        '流水号': 'nunique'
    }).reset_index()
    cat_ac['客单价'] = cat_ac['实收金额'] / cat_ac['流水号']

    fig = px.bar(cat_ac, x='商品分类', y='客单价', title='各分类客单价分析')
    return {"figure": _style(fig)}


def category_profit(sales_df, cost_ratios=None):
    """分类毛利率对比图"""
    if cost_ratios is None:
        cost_ratios = {
            '现烤': 0.35, '西点': 0.40, '手工饼干': 0.35,
            '饮品': 0.90, '生日蛋糕': 0.40, '分享蛋糕': 0.40,
            '无条码商品': 0.35, '无': 0.40
        }

    data = sales_df.copy()
    cat = data.groupby('商品分类').agg(
        销售额=('实收金额', 'sum'),
        销量=('销售数量', 'sum')
    ).reset_index()

    cat['成本比例'] = cat['商品分类'].map(cost_ratios).fillna(0.40)
    cat['原料成本'] = cat['销售额'] * cat['成本比例']
    cat['毛利'] = cat['销售额'] - cat['原料成本']
    cat['毛利率%'] = (cat['毛利'] / cat['销售额'] * 100).round(1)

    fig = px.bar(cat, x='商品分类', y='毛利率%', title='各分类毛利率',
                 text_auto='.1f', color='毛利率%',
                 color_continuous_scale='RdYlGn')
    return {"figure": _style(fig)}
