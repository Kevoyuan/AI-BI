"""
天气影响分析 — 不同天气对销售的量化影响
"""
import pandas as pd
import numpy as np


def weather_impact_summary(sales_detail_df, weather_df):
    """
    天气对销售的量化影响 — 以晴天为基准计算各天气的影响系数。

    Returns:
        DataFrame with 天气, 日均销售, 天数, 标准差, 影响系数%
    """
    df_s = sales_detail_df.copy()
    df_s['日期'] = pd.to_datetime(df_s['日期']).dt.date

    df_w = weather_df.copy()
    df_w['日期'] = pd.to_datetime(df_w['日期']).dt.date

    merged = df_s.merge(df_w, on='日期', how='inner')
    if merged.empty:
        return None

    stats = merged.groupby('天气').agg(
        日均销售=('实收金额', 'mean'),
        天数=('实收金额', 'count'),
        标准差=('实收金额', 'std'),
        中位数=('实收金额', 'median')
    ).round(0).reset_index()

    # 以晴天为基准
    baseline_row = stats[stats['天气'] == '晴天']
    baseline = baseline_row['日均销售'].values[0] if len(baseline_row) > 0 else stats['日均销售'].mean()
    stats['影响系数%'] = ((stats['日均销售'] / baseline) - 1) * 100
    stats['影响系数%'] = stats['影响系数%'].round(1)

    return stats.sort_values('日均销售', ascending=False)


def weather_category_impact(sales_df, weather_df):
    """
    天气对不同商品分类的影响 — 各种天气下各分类的日均销售。

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


def weather_alert(weather_df, sales_detail_df):
    """
    恶劣天气预警 — 检测明天是否有台风/暴雨并预估销售影响。

    Returns:
        dict with 预警级别, 预计影响, 建议
    """
    df_w = weather_df.copy()
    df_w['日期'] = pd.to_datetime(df_w['日期']).dt.date

    severe_weather = ['暴雨', '台风', '大雨']
    severe_data = df_w[df_w['天气'].isin(severe_weather)]

    if severe_data.empty:
        return {"预警": "无恶劣天气记录", "级别": "🟢 正常"}

    # 统计恶劣天气频率
    total_days = len(df_w)
    severe_days = len(severe_data)

    # 计算恶劣天气的销售影响
    df_s = sales_detail_df.copy()
    df_s['日期'] = pd.to_datetime(df_s['日期']).dt.date
    merged = df_s.merge(df_w, on='日期', how='inner')

    normal_avg = merged[merged['天气'] == '晴天']['实收金额'].mean()
    severe_avg = merged[merged['天气'].isin(severe_weather)]['实收金额'].mean()

    impact_pct = ((severe_avg / normal_avg) - 1) * 100 if normal_avg > 0 else 0

    return {
        "恶劣天气占比": f"{severe_days}/{total_days} ({severe_days/total_days*100:.1f}%)",
        "恶劣天气类型": severe_data['天气'].unique().tolist(),
        "预计影响": f"{impact_pct:+.1f}% (相对晴天)",
        "建议": "减少生产计划、提前通知客户、准备外卖预案" if impact_pct < -10 else "正常运营"
    }
