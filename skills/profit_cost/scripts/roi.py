"""
投资回报分析 — 开店 ROI、回本周期、累计回收
"""
import pandas as pd
import numpy as np


def opening_investment_summary(openning_cost_df):
    """
    开店投资总览 — 按分类汇总。

    Returns:
        dict with 总投资, 分类明细, 阶段明细
    """
    df = openning_cost_df.copy()
    df.columns = ['日期', '项目', '凭证', '金额', '阶段', '分类']

    total = df['金额'].sum()
    by_category = df.groupby('分类')['金额'].sum().sort_values(ascending=False).to_dict()
    by_phase = df.groupby('阶段')['金额'].agg(['sum', 'count']).round(0).to_dict()

    return {
        "开店总投资": round(total, 0),
        "投资分类明细": {k: round(v, 0) for k, v in by_category.items()},
        "投资阶段明细": by_phase,
    }


def payback_analysis(openning_cost_df, monthly_net_profits):
    """
    回本周期分析。

    Args:
        openning_cost_df: 开店成本表
        monthly_net_profits: 月度净利润列表（按时序排列）

    Returns:
        dict with 总投资, 累计利润, 预计回本(月), 已回收比例%
    """
    df = openning_cost_df.copy()
    total_investment = df.iloc[:, 3].sum()

    cumulative = np.cumsum(monthly_net_profits)

    # 找到回本月数
    payback_month = None
    for i, cum in enumerate(cumulative):
        if cum >= total_investment:
            payback_month = i + 1
            break

    total_recovered = cumulative[-1] if len(cumulative) > 0 else 0

    # 如果仍未回本，基于最近 3 个月平均利润估算
    if payback_month is None:
        recent_avg = np.mean(monthly_net_profits[-3:]) if len(monthly_net_profits) >= 3 else np.mean(monthly_net_profits)
        if recent_avg > 0:
            remaining = total_investment - total_recovered
            payback_month = len(monthly_net_profits) + (remaining / recent_avg)

    return {
        "开店总投资": round(total_investment, 0),
        "累计回收": round(total_recovered, 0),
        "已运营月数": len(monthly_net_profits),
        "预计回本(月)": round(payback_month, 1) if payback_month else "无法回本",
        "已回收比例%": round(total_recovered / total_investment * 100, 1) if total_investment > 0 else 0,
        "月均净利润(近3月)": round(np.mean(monthly_net_profits[-3:]), 0) if len(monthly_net_profits) >= 3 else round(np.mean(monthly_net_profits), 0),
    }


def cost_structure_analysis(sales_detail_df, sales_df, loss_df, financial_params):
    """
    成本结构分析 — 各成本项的占比。

    Returns:
        dict with 各成本项的金额和占营收比例
    """
    from modules.config import CATEGORY_COST_RATIOS

    revenue = sales_detail_df['实收金额'].sum()

    s = sales_df.copy()
    s['成本率'] = s['商品分类'].map(CATEGORY_COST_RATIOS).fillna(CATEGORY_COST_RATIOS['default'])
    material_cost = (s['商品总价'] * s['成本率']).sum()

    opex_cost = revenue * financial_params.get("运营管理", 0.0438)
    fixed_cost = financial_params.get("固定支出", 5000)

    l = loss_df.copy()
    l['备注'] = l['备注'].fillna('')
    waste_cost = l.loc[~l['备注'].str.contains('试吃', na=False), '报损金额'].sum()

    total_cost = material_cost + opex_cost + fixed_cost + waste_cost

    return {
        "原料成本": {"金额": round(material_cost, 0), "占比%": round(material_cost / revenue * 100, 1) if revenue > 0 else 0},
        "运营管理": {"金额": round(opex_cost, 0), "占比%": round(opex_cost / revenue * 100, 1) if revenue > 0 else 0},
        "固定支出": {"金额": round(fixed_cost, 0), "占比%": round(fixed_cost / revenue * 100, 1) if revenue > 0 else 0},
        "报废损耗": {"金额": round(waste_cost, 0), "占比%": round(waste_cost / revenue * 100, 1) if revenue > 0 else 0},
        "成本合计": {"金额": round(total_cost, 0), "占比%": round(total_cost / revenue * 100, 1) if revenue > 0 else 0},
        "净利润": {"金额": round(revenue - total_cost, 0), "占比%": round((revenue - total_cost) / revenue * 100, 1) if revenue > 0 else 0},
    }
