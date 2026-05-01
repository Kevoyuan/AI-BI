"""
ROI Analysis — startup investment summary, payback period, cost structure.
"""
import pandas as pd
import numpy as np


def investment_summary(opening_cost_df: pd.DataFrame) -> dict:
    """
    Summarise startup investment by category and phase.

    Returns:
        dict with total_investment, by_category, by_phase
    """
    df = opening_cost_df.copy()
    if df.empty:
        return {"total_investment": 0, "by_category": {}, "by_phase": {}}

    # Standardise column names (original has: date, item, voucher, amount, phase, category)
    expected_cols = ["date", "item", "voucher", "amount", "phase", "category"]
    if len(df.columns) >= 6:
        df.columns = expected_cols[: len(df.columns)]
    elif "amount" not in df.columns:
        num_cols = df.select_dtypes(include=[np.number]).columns
        if len(num_cols) > 0:
            df = df.rename(columns={num_cols[0]: "amount"})

    total = float(df["amount"].sum())

    by_category = (
        df.groupby("category")["amount"]
        .sum()
        .sort_values(ascending=False)
        .to_dict()
        if "category" in df.columns
        else {}
    )

    by_phase = (
        df.groupby("phase")["amount"]
        .agg(["sum", "count"])
        .round(0)
        .to_dict()
        if "phase" in df.columns
        else {}
    )

    return {
        "total_investment": round(total, 0),
        "by_category": {k: round(v, 0) for k, v in by_category.items()},
        "by_phase": by_phase,
    }


def payback_analysis(
    opening_cost_df: pd.DataFrame,
    monthly_net_profits: list,
) -> dict:
    """
    Calculate payback period based on cumulative monthly net profits.

    Args:
        opening_cost_df: Startup cost ledger.
        monthly_net_profits: list of floats — monthly net profit values in time order.

    Returns:
        dict with total_investment, cumulative_profit, payback_months,
        recovery_pct, avg_monthly_profit
    """
    summary = investment_summary(opening_cost_df)
    total_investment = summary["total_investment"]

    if not monthly_net_profits:
        return {
            "total_investment": total_investment,
            "cumulative_profit": 0,
            "months_operated": 0,
            "payback_months": "insufficient data",
            "recovery_pct": 0,
        }

    cumulative = np.cumsum(monthly_net_profits)

    payback_month = None
    for i, cum in enumerate(cumulative):
        if cum >= total_investment:
            payback_month = i + 1
            break

    total_recovered = float(cumulative[-1])

    # Estimate if not yet paid back
    if payback_month is None:
        recent = monthly_net_profits[-3:] if len(monthly_net_profits) >= 3 else monthly_net_profits
        recent_avg = float(np.mean(recent))
        if recent_avg > 0:
            remaining = total_investment - total_recovered
            payback_month = len(monthly_net_profits) + (remaining / recent_avg)

    return {
        "total_investment": round(total_investment, 0),
        "cumulative_profit": round(total_recovered, 0),
        "months_operated": len(monthly_net_profits),
        "payback_months": round(payback_month, 1) if payback_month else "not_recoverable",
        "recovery_pct": round(total_recovered / total_investment * 100, 1) if total_investment > 0 else 0,
        "avg_monthly_profit_recent3": round(
            float(np.mean(monthly_net_profits[-3:])), 0
        ) if len(monthly_net_profits) >= 3 else round(float(np.mean(monthly_net_profits)), 0),
    }


def cost_structure_analysis(
    sales_detail_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    waste_df: pd.DataFrame,
    financial_params: dict,
) -> dict:
    """
    Analyse cost structure — each cost item's share of total revenue.

    Returns:
        dict of cost items, each with amount and revenue_share_pct
    """
    from skills.profit_cost.scripts.profit import CATEGORY_COST_RATIOS

    amount_col = "amount" if "amount" in sales_detail_df.columns else "revenue"
    revenue = float(sales_detail_df[amount_col].sum())

    s = sales_df.copy()
    s["cost_ratio"] = s.get("category", pd.Series(dtype=str)).map(CATEGORY_COST_RATIOS).fillna(CATEGORY_COST_RATIOS["default"])
    price_col = "total_price" if "total_price" in s.columns else "amount"
    material_cost = float((s[price_col] * s["cost_ratio"]).sum())

    opex_cost = revenue * financial_params.get("opex_ratio", 0.044)
    fixed_cost = financial_params.get("fixed_cost", 1500)

    w = waste_df.copy()
    note_col = "note" if "note" in w.columns else w.columns[-1] if not w.empty else "note"
    w[note_col] = w.get(note_col, pd.Series(dtype=str)).fillna("")
    waste_amt_col = "waste_amount" if "waste_amount" in w.columns else "amount"
    waste_cost = float(w.loc[~w[note_col].str.contains("sample", case=False, na=False), waste_amt_col].sum()) if not w.empty else 0

    total_cost = material_cost + opex_cost + fixed_cost + waste_cost

    def _item(amount):
        return {
            "amount": round(amount, 0),
            "revenue_share_pct": round(amount / revenue * 100, 1) if revenue > 0 else 0,
        }

    return {
        "material_cost": _item(material_cost),
        "opex": _item(opex_cost),
        "fixed_cost": _item(fixed_cost),
        "waste_loss": _item(waste_cost),
        "total_cost": _item(total_cost),
        "net_profit": _item(revenue - total_cost),
    }
