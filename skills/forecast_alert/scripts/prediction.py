"""
销售预测 — 加权移动平均、线性回归、星期因子
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from numpy.polynomial.polynomial import polyfit


def predict_tomorrow(sales_detail_df, anchor_date=None):
    """
    预测明天销售额 — 近 4 周同星期加权平均。

    Args:
        sales_detail_df: 包含 日期 与 实收金额 的销售 DataFrame
        anchor_date: 基准日期（默认使用数据中最大日期或当前系统日期）

    Returns:
        dict with 预测, 置信下限, 置信上限, 近4周同天数据
    """
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])
    df['星期'] = df['日期'].dt.dayofweek

    if anchor_date is not None:
        anchor_dt = pd.to_datetime(anchor_date).date()
    elif not df.empty and df['日期'].notna().any():
        anchor_dt = df['日期'].max().date()
    else:
        anchor_dt = datetime.now().date()

    tomorrow = anchor_dt + timedelta(days=1)
    tomorrow_dow = tomorrow.weekday()

    same_dow = df[(df['日期'].dt.date <= anchor_dt) & (df['星期'] == tomorrow_dow)]
    if same_dow.empty:
        return {"error": f"无周{['一','二','三','四','五','六','日'][tomorrow_dow]}历史同星期数据"}

    recent = same_dow.groupby(same_dow['日期'].dt.date)['实收金额'].sum()
    recent = recent.sort_index().tail(4)

    weights = np.array([0.15, 0.20, 0.30, 0.35])
    n = len(recent)
    w = weights[-n:] / weights[-n:].sum()

    predicted = np.dot(recent.values, w)
    std = recent.std() if n > 1 else 0.0
    if pd.isna(std):
        std = 0.0

    return {
        "基准日期": str(anchor_dt),
        "预测目标日期": str(tomorrow),
        "目标星期": f"周{['一','二','三','四','五','六','日'][tomorrow_dow]}",
        "预测明天销售额": round(predicted, 0),
        "置信下限": round(max(0, predicted - std), 0),
        "置信上限": round(predicted + std, 0),
        "基于": f"近{n}个同星期",
        "参考数据": {str(k): round(float(v), 2) for k, v in recent.to_dict().items()}
    }


def predict_next_week(sales_detail_df):
    """预测下周销售额 — 近 8 周线性回归 + 最近一周基准。"""
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])
    df['周'] = df['日期'].dt.isocalendar().week.astype(int)
    df['年'] = df['日期'].dt.isocalendar().year.astype(int)

    weekly = df.groupby(['年', '周'])['实收金额'].sum().reset_index()
    weekly['周序数'] = range(len(weekly))

    coefs = np.polyfit(weekly['周序数'], weekly['实收金额'], 1)
    trend_fn = np.poly1d(coefs)
    last_week_value = weekly['实收金额'].iloc[-1]
    predicted = trend_fn(len(weekly))
    blended = last_week_value * 0.6 + predicted * 0.4

    return {
        "预测下周销售额": round(blended, 0),
        "纯趋势预测": round(predicted, 0),
        "上周实际": round(last_week_value, 0),
        "趋势方向": "上升" if coefs[0] > 0 else "下降",
        "周均变化": round(coefs[0], 0)
    }


def predict_next_month(sales_detail_df):
    """预测下月销售额 — 12 个月线性趋势 + 月度季节性调整。"""
    df = sales_detail_df.copy()
    df['日期'] = pd.to_datetime(df['日期'])
    df['月份'] = df['日期'].dt.to_period('M')

    monthly = df.groupby('月份')['实收金额'].sum().reset_index()
    monthly['月份序数'] = range(len(monthly))

    coefs = np.polyfit(monthly['月份序数'], monthly['实收金额'], 1)
    trend_fn = np.poly1d(coefs)
    predicted_vals = trend_fn(monthly['月份序数'])
    ss_res = ((monthly['实收金额'] - predicted_vals) ** 2).sum()
    ss_tot = ((monthly['实收金额'] - monthly['实收金额'].mean()) ** 2).sum()
    r_squared = 1 - ss_res / ss_tot
    predicted = trend_fn(len(monthly))

    return {
        "预测下月销售额": round(predicted, 0),
        "趋势方向": "上升" if coefs[0] > 0 else "下降",
        "月均变化量": round(coefs[0], 0),
        "R²": round(r_squared, 3),
        "置信度": "高" if r_squared > 0.7 else ("中" if r_squared > 0.4 else "低")
    }
