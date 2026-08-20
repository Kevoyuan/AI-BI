"""
盈亏平衡分析 — 计算保本点、安全边际
"""
import pandas as pd
import numpy as np


def breakeven_analysis(openning_cost_df, financial_params, monthly_revenue):
    """
    盈亏平衡分析。

    Args:
        openning_cost_df: 开店成本表
        financial_params: dict with 固定支出, 原料成本比, 运营管理
        monthly_revenue: 月销售额（用于安全边际计算）

    Returns:
        dict with 变动成本率, 边际贡献率, 月度固定成本, 开店总投入,
        月摊销, 盈亏平衡月销售额, 盈亏平衡日销售额, 安全边际率
    """
    material_ratio = financial_params.get("原料成本比", 0.40)
    opex_ratio = financial_params.get("运营管理", 0.0438)
    monthly_fixed = financial_params.get("固定支出", 5000)

    variable_cost_ratio = material_ratio + opex_ratio
    contribution_margin_ratio = 1 - variable_cost_ratio

    # 开店成本摊销（3 年 = 36 个月）
    total_opening = openning_cost_df.iloc[:, 3].sum() if not openning_cost_df.empty else 0
    monthly_amortization = total_opening / 36

    total_fixed = monthly_fixed + monthly_amortization
    be_revenue = total_fixed / contribution_margin_ratio if contribution_margin_ratio > 0 else float('inf')

    # 安全边际
    safety_margin = ((monthly_revenue - be_revenue) / monthly_revenue * 100) if monthly_revenue > 0 else 0

    return {
        "变动成本率%": round(variable_cost_ratio * 100, 1),
        "边际贡献率%": round(contribution_margin_ratio * 100, 1),
        "月度固定支出": round(monthly_fixed, 0),
        "开店总投入": round(total_opening, 0),
        "3年月摊销": round(monthly_amortization, 0),
        "月度固定成本合计": round(total_fixed, 0),
        "盈亏平衡月销售额": round(be_revenue, 0),
        "盈亏平衡日销售额": round(be_revenue / 30, 0),
        "当前月销售额": round(monthly_revenue, 0),
        "安全边际率%": round(safety_margin, 1),
        "状态": "盈利" if monthly_revenue > be_revenue else "亏损"
    }


def daily_breakeven(fixed_cost, variable_cost_ratio):
    """
    简化版日盈亏平衡点。

    Args:
        fixed_cost: 日固定成本
        variable_cost_ratio: 变动成本率

    Returns:
        float: 日盈亏平衡销售额
    """
    cm_ratio = 1 - variable_cost_ratio
    return fixed_cost / cm_ratio if cm_ratio > 0 else float('inf')
