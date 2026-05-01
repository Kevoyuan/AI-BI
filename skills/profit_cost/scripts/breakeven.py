"""
Break-Even Analysis — compute break-even revenue, safety margin.
"""
import pandas as pd
import numpy as np


def breakeven_analysis(
    opening_cost_df: pd.DataFrame,
    financial_params: dict,
    monthly_revenue: float,
) -> dict:
    """
    Break-even point analysis.

    Args:
        opening_cost_df: Startup cost ledger.
        financial_params: dict with fixed_cost, material_ratio, opex_ratio.
        monthly_revenue: Current month's revenue (for safety margin calc).

    Returns:
        dict with variable_cost_ratio, contribution_margin, monthly_fixed,
        total_investment, monthly_amortisation, breakeven_revenue, safety_margin
    """
    material_ratio = financial_params.get("material_ratio", 0.40)
    opex_ratio = financial_params.get("opex_ratio", 0.044)
    monthly_fixed = financial_params.get("fixed_cost", 1500)

    variable_cost_ratio = material_ratio + opex_ratio
    contribution_margin_ratio = 1 - variable_cost_ratio

    # Amortise startup costs over 36 months (3 years)
    total_opening = 0
    if not opening_cost_df.empty:
        # Find the numeric column (amount)
        num_cols = opening_cost_df.select_dtypes(include=[np.number]).columns
        if len(num_cols) > 0:
            total_opening = float(opening_cost_df[num_cols[0]].sum())

    monthly_amortisation = total_opening / 36

    total_fixed = monthly_fixed + monthly_amortisation
    be_revenue = total_fixed / contribution_margin_ratio if contribution_margin_ratio > 0 else float("inf")

    safety_margin = (
        (monthly_revenue - be_revenue) / monthly_revenue * 100
        if monthly_revenue > 0
        else 0
    )

    return {
        "variable_cost_ratio_pct": round(variable_cost_ratio * 100, 1),
        "contribution_margin_pct": round(contribution_margin_ratio * 100, 1),
        "monthly_fixed_cost": round(monthly_fixed, 0),
        "total_investment": round(total_opening, 0),
        "monthly_amortisation": round(monthly_amortisation, 0),
        "total_monthly_fixed": round(total_fixed, 0),
        "breakeven_monthly_revenue": round(be_revenue, 0),
        "breakeven_daily_revenue": round(be_revenue / 30, 0),
        "current_monthly_revenue": round(monthly_revenue, 0),
        "safety_margin_pct": round(safety_margin, 1),
        "status": "profitable" if monthly_revenue > be_revenue else "below_breakeven",
    }


def daily_breakeven(fixed_cost: float, variable_cost_ratio: float) -> float:
    """
    Simplified daily break-even revenue.

    Args:
        fixed_cost: Daily fixed cost.
        variable_cost_ratio: Sum of material + opex ratios (0-1).

    Returns:
        float — daily revenue needed to break even.
    """
    cm_ratio = 1 - variable_cost_ratio
    return fixed_cost / cm_ratio if cm_ratio > 0 else float("inf")
