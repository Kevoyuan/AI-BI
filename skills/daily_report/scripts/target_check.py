"""
目标对比 — 按星期几对比实际业绩与目标值
"""
import pandas as pd
from datetime import datetime


WEEKDAY_TARGETS = {
    "周一": {"revenue": 14000, "tc": 350, "card": 4000, "cash": 13000},
    "周二": {"revenue": 14000, "tc": 350, "card": 4000, "cash": 13000},
    "周三": {"revenue": 14000, "tc": 350, "card": 4000, "cash": 13000},
    "周四": {"revenue": 14000, "tc": 350, "card": 4000, "cash": 13000},
    "周五": {"revenue": 16000, "tc": 400, "card": 5000, "cash": 14800},
    "周六": {"revenue": 24000, "tc": 600, "card": 6000, "cash": 23000},
    "周日": {"revenue": 28000, "tc": 700, "card": 6000, "cash": 26800},
}


def check_target(daily_summary_df, date=None):
    """
    对比实际 vs 目标。

    Args:
        daily_summary_df: calculate_daily_summary 的输出
        date: 指定日期（格式 "YYYY-MM-DD 周X"），不指定则取最新一天

    Returns:
        dict with 销售额, 目标, 达成率, TC, 目标TC, TC达成率
    """
    df = daily_summary_df.copy()
    if date:
        row = df[df["日期"].str.startswith(date)]
    else:
        row = df.tail(1)

    if row.empty:
        return {"error": "无数据"}

    date_str = row.iloc[0]["日期"]
    weekday = date_str.split(" ")[-1] if " " in date_str else "未知"
    target = WEEKDAY_TARGETS.get(weekday, WEEKDAY_TARGETS["周一"])

    revenue = row.iloc[0]["实收金额"]
    tc = row.iloc[0]["订单笔数"]

    return {
        "日期": date_str,
        "星期": weekday,
        "销售额": revenue,
        "目标销售额": target["revenue"],
        "达成率": f'{revenue / target["revenue"] * 100:.1f}%',
        "TC": tc,
        "目标TC": target["tc"],
        "TC达成率": f'{tc / target["tc"] * 100:.1f}%',
        "偏差": f'{(revenue / target["revenue"] - 1) * 100:+.1f}%',
    }
