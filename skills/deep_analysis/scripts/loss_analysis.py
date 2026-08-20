"""
报废分析 — 报废分类统计、报废率、报废原因分析
"""
import pandas as pd
import numpy as np


def categorize_loss(loss_df):
    """
    将报废数据分类：现烤报废、西点报废、试吃、股东带走、非正常报废。

    Returns:
        dict with DataFrames keyed by category
    """
    df = loss_df.copy()
    df['备注'] = df['备注'].fillna('')

    categories = {}

    # 试吃
    mask_tasting = (
        df['备注'].str.contains('试吃', na=False)
        | (df['报损原因'].shift(-1).fillna('') == '试吃')
    )
    categories['试吃'] = df[mask_tasting]

    # 现烤报废（不含试吃）
    mask_xiankao = (
        df['备注'].str.contains('现烤', na=False)
        & ~df['备注'].str.contains('试吃', na=False)
        & (df['报损原因'].shift(-1).fillna('') != '试吃')
    )
    categories['现烤报废'] = df[mask_xiankao]

    # 西点报废（不含试吃）
    mask_xidian = (
        df['备注'].str.contains('西点|蛋糕', na=False)
        & ~df['备注'].str.contains('试吃', na=False)
        & (df['报损原因'].shift(-1).fillna('') != '试吃')
    )
    categories['西点报废'] = df[mask_xidian]

    # 股东带走
    mask_shareholder = df['备注'].str.contains('带走|股东', na=False)
    categories['股东带走'] = df[mask_shareholder]

    # 非正常报废
    mask_abnormal = df['备注'].str.contains('非正常', na=False)
    categories['非正常报废'] = df[mask_abnormal]

    return categories


def waste_rate_trend(loss_df, sales_detail_df):
    """
    报废率趋势 = 非试吃报损金额 / 销售额。

    Returns:
        DataFrame with 日期, 报废金额, 销售额, 报废率%
    """
    df_l = loss_df.copy()
    df_l = df_l[~df_l['备注'].str.contains('试吃', na=False)]
    daily_loss = df_l.groupby('调整日期')['报损金额'].sum().reset_index()
    daily_loss.columns = ['日期', '报废金额']

    df_s = sales_detail_df.copy()
    df_s['日期'] = pd.to_datetime(df_s['日期']).dt.date
    daily_sales = df_s.groupby('日期')['实收金额'].sum().reset_index()

    merged = daily_loss.merge(daily_sales, on='日期', how='inner')
    merged['报废率%'] = (merged['报废金额'] / merged['实收金额'] * 100).round(2)

    return merged


def loss_reason_breakdown(loss_df):
    """
    报废原因拆解。

    Returns:
        DataFrame with 报损原因, 金额, 占比
    """
    df = loss_df.copy()
    df = df[~df['备注'].str.contains('试吃', na=False)]

    breakdown = df.groupby('报损原因').agg(
        金额=('报损金额', 'sum'),
        次数=('报损金额', 'count')
    ).reset_index().sort_values('金额', ascending=False)

    total = breakdown['金额'].sum()
    breakdown['占比%'] = (breakdown['金额'] / total * 100).round(1) if total > 0 else 0

    return breakdown
