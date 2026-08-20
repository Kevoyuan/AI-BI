"""
异常检测 — Z-Score、IQR、连续下降、目标偏离
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def zscore_anomalies(sales_detail_df, sigma=2.0):
    """
    Z-Score 异常检测 — 偏离均值超过 N 个标准差。

    Returns:
        DataFrame with 日期, 销售额, Z值, 偏离均值%
    """
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])

    daily = df.groupby(df['日期'].dt.date)['实收金额'].sum()
    mean = daily.mean()
    std = daily.std()

    zscore = (daily - mean) / std
    anomalies = daily[abs(zscore) > sigma]

    if anomalies.empty:
        return pd.DataFrame(columns=['日期', '销售额', 'Z值', '偏离均值%'])

    result = pd.DataFrame({
        '日期': anomalies.index,
        '销售额': anomalies.values,
        'Z值': zscore[abs(zscore) > sigma].round(2),
        '偏离均值%': ((anomalies.values - mean) / mean * 100).round(1)
    })

    return result.sort_values('Z值')


def iqr_anomalies(sales_detail_df):
    """
    IQR 异常检测 — 超出 Q1-1.5*IQR 或 Q3+1.5*IQR。

    Returns:
        DataFrame with 日期, 销售额, 类型
    """
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])

    daily = df.groupby(df['日期'].dt.date)['实收金额'].sum()

    q1 = daily.quantile(0.25)
    q3 = daily.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    low = daily[daily < lower]
    high = daily[daily > upper]

    results = []
    for date, val in low.items():
        results.append({'日期': date, '销售额': val, '类型': '异常低'})
    for date, val in high.items():
        results.append({'日期': date, '销售额': val, '类型': '异常高'})

    return pd.DataFrame(results)


def consecutive_decline(sales_detail_df):
    """
    检测销售额连续下降趋势。

    Returns:
        dict with 当前连续下降天数, 历史最长连续下降, 预警级别, 下降起始日期
    """
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])

    daily = df.groupby(df['日期'].dt.date)['实收金额'].sum()

    consecutive = 0
    max_consecutive = 0
    current_start = None
    all_streaks = []

    for i in range(1, len(daily)):
        if daily.iloc[i] < daily.iloc[i - 1]:
            if consecutive == 0:
                current_start = daily.index[i - 1]
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            if consecutive > 0:
                all_streaks.append({
                    'start': str(current_start),
                    'end': str(daily.index[i - 1]),
                    'days': consecutive
                })
            consecutive = 0

    # 仍在下降中
    if consecutive > 0:
        all_streaks.append({
            'start': str(current_start),
            'end': str(daily.index[-1]),
            'days': consecutive
        })

    level = '🔴 高危' if consecutive >= 5 else ('🟡 关注' if consecutive >= 3 else '🟢 正常')

    return {
        "当前连续下降天数": consecutive,
        "历史最长连续下降": max_consecutive,
        "预警级别": level,
        "下降历史": all_streaks[-5:]  # 最近 5 段
    }


def target_deviation_check(daily_revenue, weekday, targets):
    """
    检查目标偏离程度。

    Args:
        daily_revenue: 当日销售额
        weekday: 星期名（周一~周日）
        targets: WEEKDAY_TARGETS dict

    Returns:
        dict with 偏离率, 预警级别
    """
    target = targets.get(weekday, {}).get('revenue', 14000)
    deviation = (daily_revenue / target - 1) * 100

    if deviation < -20:
        level = '🔴 高危'
    elif deviation < -10:
        level = '🟠 警告'
    elif deviation < 0:
        level = '🟡 略低'
    elif deviation > 20:
        level = '🟢 超额'
    else:
        level = '🟢 正常'

    return {
        "实际": daily_revenue,
        "目标": target,
        "偏离率%": round(deviation, 1),
        "预警级别": level
    }
