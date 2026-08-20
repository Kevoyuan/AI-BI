"""
关联分析 — 天气-销售关联、分类间关联、跨表关联
"""
import pandas as pd
import numpy as np


def weather_sales_correlation(sales_detail_df, weather_df):
    """
    天气对销售的影响分析。

    Returns:
        DataFrame with 天气, 日均销售, 天数, 标准差, 中位数, 影响系数%
    """
    df_s = sales_detail_df.copy()
    df_s['日期'] = pd.to_datetime(df_s['日期']).dt.date

    df_w = weather_df.copy()
    df_w['日期'] = pd.to_datetime(df_w['日期']).dt.date

    merged = df_s.merge(df_w, on='日期', how='inner')

    if merged.empty:
        return None

    stats_df = merged.groupby('天气').agg(
        日均销售=('实收金额', 'mean'),
        天数=('实收金额', 'count'),
        标准差=('实收金额', 'std'),
        中位数=('实收金额', 'median')
    ).round(0).reset_index()

    # 以多云为基准（最常见的天气）
    baseline_row = stats_df[stats_df['天气'] == '多云']
    baseline = baseline_row['日均销售'].values[0] if len(baseline_row) > 0 else stats_df['日均销售'].mean()
    stats_df['影响系数%'] = ((stats_df['日均销售'] / baseline) - 1 * 100).round(1)

    return stats_df.sort_values('日均销售', ascending=False)


def weather_category_correlation(sales_df, weather_df):
    """
    天气对不同商品分类的影响。

    Returns:
        DataFrame with 天气, 商品分类, 日均销售
    """
    df_s = sales_df.copy()
    df_s['销售时间'] = pd.to_datetime(df_s['销售时间'])
    df_s['日期'] = df_s['销售时间'].dt.date

    df_w = weather_df.copy()
    df_w['日期'] = pd.to_datetime(df_w['日期']).dt.date

    merged = df_s.merge(df_w, on='日期', how='inner')

    if merged.empty:
        return None

    stats = merged.groupby(['天气', '商品分类'])['实收金额'].mean().round(0).reset_index()
    stats.columns = ['天气', '商品分类', '日均销售']

    return stats


def cross_period_comparison(sales_detail_df, period1_label, period1_dates, period2_label, period2_dates):
    """
    两个时期的销售对比。

    Args:
        sales_detail_df: 销售明细
        period1_label: 时期1名称（如 "本月"）
        period1_dates: 时期1日期列表
        period2_label: 时期2名称（如 "上月"）
        period2_dates: 时期2日期列表

    Returns:
        dict with comparison metrics
    """
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期']).dt.date

    p1 = df[df['日期'].isin(period1_dates)]
    p2 = df[df['日期'].isin(period2_dates)]

    p1_total = p1['实收金额'].sum()
    p2_total = p2['实收金额'].sum()
    change = (p1_total - p2_total) / p2_total * 100 if p2_total > 0 else 0

    return {
        f'{period1_label}销售额': p1_total,
        f'{period2_label}销售额': p2_total,
        '变化率%': round(change, 1),
        f'{period1_label}日均': p1['实收金额'].mean(),
        f'{period2_label}日均': p2['实收金额'].mean(),
    }
