"""
销售预测 — 加权移动平均、线性回归、星期因子
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from numpy.polynomial.polynomial import polyfit


def predict_tomorrow(sales_detail_df):
    """
    预测明天销售额 — 近 4 周同星期加权平均。

    Returns:
        dict with 预测, 置信下限, 置信上限, 近4周同天数据
    """
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])
    df['星期'] = df['日期'].dt.dayofweek

    tomorrow_dow = (datetime.now() + timedelta(days=1)).weekday()

    same_dow = df[df['星期'] == tomorrow_dow]
    if same_dow.empty:
        return {"error": "无同星期历史数据"}

    recent = same_dow.groupby(same_dow['日期'].dt.date)['实收金额'].sum()
    recent = recent.sort_index().tail(4)

    weights = np.array([0.15, 0.20, 0.30, 0.35])  # 越近权重越大
    n = len(recent)
    w = weights[-n:] / weights[-n:].sum()

    predicted = np.dot(recent.values, w)
    std = recent.std()

    return {
        "预测明天销售额": round(predicted, 0),
        "置信下限": round(predicted - std, 0),
        "置信上限": round(predicted + std, 0),
        "基于": f"近{n}个同星期",
        "参考数据": recent.to_dict()
    }


def predict_next_week(sales_detail_df):
    """
    预测下周销售额 — 近 8 周线性回归 + 最近一周基准。

    Returns:
        dict with 预测, 趋势方向, 上周实际
    """
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])

    # 按周汇总
    df['周'] = df['日期'].dt.isocalendar().week.astype(int)
    df['年'] = df['日期'].dt.isocalendar().year.astype(int)

    weekly = df.groupby(['年', '周'])['实收金额'].sum().reset_index()
    weekly['周序数'] = range(len(weekly))

    # 线性回归
    coefs = np.polyfit(weekly['周序数'], weekly['实收金额'], 1)
    trend_fn = np.poly1d(coefs)

    last_week_value = weekly['实收金额'].iloc[-1]
    next_idx = len(weekly)
    predicted = trend_fn(next_idx)

    # 结合最近一周基准和趋势预测
    blended = last_week_value * 0.6 + predicted * 0.4

    return {
        "预测下周销售额": round(blended, 0),
        "纯趋势预测": round(predicted, 0),
        "上周实际": round(last_week_value, 0),
        "趋势方向": "上升" if coefs[0] > 0 else "下降",
        "周均变化": round(coefs[0], 0)
    }


def predict_next_month(sales_detail_df):
    """
    预测下月销售额 — 12 个月线性趋势 + 月度季节性调整。

    Returns:
        dict with 预测, 趋势, R²
    """
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])
    df['月份'] = df['日期'].dt.to_period('M')

    monthly = df.groupby('月份')['实收金额'].sum().reset_index()
    monthly['月份序数'] = range(len(monthly))

    coefs = np.polyfit(monthly['月份序数'], monthly['实收金额'], 1)
    trend_fn = np.poly1d(coefs)

    # R²
    predicted_vals = trend_fn(monthly['月份序数'])
    ss_res = ((monthly['实收金额'] - predicted_vals) ** 2).sum()
    ss_tot = ((monthly['实收金额'] - monthly['实收金额'].mean()) ** 2).sum()
    r_squared = 1 - ss_res / ss_tot

    next_idx = len(monthly)
    predicted = trend_fn(next_idx)

    return {
        "预测下月销售额": round(predicted, 0),
        "趋势方向": "上升" if coefs[0] > 0 else "下降",
        "月均变化量": round(coefs[0], 0),
        "R²": round(r_squared, 3),
        "置信度": "高" if r_squared > 0.7 else ("中" if r_squared > 0.4 else "低")
    }
