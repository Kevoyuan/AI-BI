"""
利润计算 — 综合利润表、分类盈利分析、利润率趋势
"""
import pandas as pd
import numpy as np
from modules.config import CATEGORY_COST_RATIOS


def comprehensive_pl(sales_detail_df, sales_df, loss_df, financial_params):
    """
    综合利润表 (P&L)。

    Args:
        sales_detail_df: 订单销售明细
        sales_df: 商品销售明细（用于分类成本）
        loss_df: 报损数据
        financial_params: dict with 固定支出, 原料成本比, 运营管理

    Returns:
        dict with 营业收入, 原料成本, 毛利, 毛利率, 运营管理成本,
        固定支出, 报废损耗, 运营利润, 运营利润率, 净利润, 净利率
    """
    revenue = sales_detail_df['实收金额'].sum()
    material_ratio = financial_params.get("原料成本比", 0.40)
    opex_ratio = financial_params.get("运营管理", 0.0438)
    fixed_cost = financial_params.get("固定支出", 5000)

    # 按分类精确计算原料成本
    s = sales_df.copy()
    s['成本率'] = s['商品分类'].map(CATEGORY_COST_RATIOS).fillna(CATEGORY_COST_RATIOS['default'])
    s['商品成本'] = s['商品总价'] * s['成本率']
    material_cost = s['商品成本'].sum()

    # 毛利
    gross_profit = revenue - material_cost
    gross_margin = (gross_profit / revenue * 100) if revenue > 0 else 0

    # 运营管理成本
    opex_cost = revenue * opex_ratio

    # 运营利润
    operating_profit = gross_profit - opex_cost - fixed_cost
    operating_margin = (operating_profit / revenue * 100) if revenue > 0 else 0

    # 报废损耗（非试吃）
    l = loss_df.copy()
    l['备注'] = l['备注'].fillna('')
    mask_waste = ~l['备注'].str.contains('试吃', na=False)
    waste_cost = l.loc[mask_waste, '报损金额'].sum()

    # 净利润
    net_profit = operating_profit - waste_cost
    net_margin = (net_profit / revenue * 100) if revenue > 0 else 0

    return {
        "营业收入": round(revenue, 0),
        "原料成本": round(material_cost, 0),
        "毛利": round(gross_profit, 0),
        "毛利率%": round(gross_margin, 1),
        "运营管理成本": round(opex_cost, 0),
        "固定支出": round(fixed_cost, 0),
        "报废损耗": round(waste_cost, 0),
        "运营利润": round(operating_profit, 0),
        "运营利润率%": round(operating_margin, 1),
        "净利润": round(net_profit, 0),
        "净利率%": round(net_margin, 1),
    }


def category_profit_analysis(sales_df):
    """
    各分类盈利分析。

    Returns:
        DataFrame with 商品分类, 销售额, 销量, 商品数, 成本比例, 原料成本, 毛利, 毛利率%, 销售额占比%
    """
    df = sales_df.copy()

    cat = df.groupby('商品分类').agg(
        销售额=('实收金额', 'sum'),
        销量=('销售数量', 'sum'),
        商品数=('商品名称', 'nunique')
    ).reset_index()

    cat['成本比例'] = cat['商品分类'].map(CATEGORY_COST_RATIOS).fillna(CATEGORY_COST_RATIOS['default'])
    cat['原料成本'] = cat['销售额'] * cat['成本比例']
    cat['毛利'] = cat['销售额'] - cat['原料成本']
    cat['毛利率%'] = (cat['毛利'] / cat['销售额'] * 100).round(1)
    cat['销售额占比%'] = (cat['销售额'] / cat['销售额'].sum() * 100).round(1)

    return cat.sort_values('毛利', ascending=False)


def profit_trend(sales_detail_df, sales_df, financial_params):
    """
    月度利润趋势。

    Returns:
        DataFrame with 月份, 营业收入, 原料成本, 毛利, 净利润, 净利率%
    """
    df_d = sales_detail_df.copy()
    df_d['日期'] = pd.to_datetime(df_d['日期'])
    df_d['月份'] = df_d['日期'].dt.to_period('M')

    df_s = sales_df.copy()
    df_s['销售时间'] = pd.to_datetime(df_s['销售时间'])
    df_s['月份'] = df_s['销售时间'].dt.to_period('M')
    df_s['成本率'] = df_s['商品分类'].map(CATEGORY_COST_RATIOS).fillna(CATEGORY_COST_RATIOS['default'])
    df_s['商品成本'] = df_s['商品总价'] * df_s['成本率']

    opex_ratio = financial_params.get("运营管理", 0.0438)
    fixed_cost = financial_params.get("固定支出", 5000)

    monthly_rev = df_d.groupby('月份')['实收金额'].sum()
    monthly_cost = df_s.groupby('月份')['商品成本'].sum()

    trend = pd.DataFrame({
        '营业收入': monthly_rev,
        '原料成本': monthly_cost,
    })
    trend['毛利'] = trend['营业收入'] - trend['原料成本']
    trend['运营管理成本'] = trend['营业收入'] * opex_ratio
    trend['固定支出'] = fixed_cost
    trend['净利润'] = trend['毛利'] - trend['运营管理成本'] - trend['固定支出']
    trend['净利率%'] = (trend['净利润'] / trend['营业收入'] * 100).round(1)

    return trend.reset_index()
