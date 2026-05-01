"""
Profit Calculation — comprehensive P&L, category profitability, profit trend.
"""
import pandas as pd
import numpy as np


# Default cost ratios per category (can be overridden via config)
CATEGORY_COST_RATIOS = {
    "fresh_baked": 0.35,
    "pastry": 0.38,
    "cookies": 0.30,
    "beverages": 0.25,
    "cake": 0.40,
    "default": 0.35,
}


def comprehensive_pl(
    sales_detail_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    waste_df: pd.DataFrame,
    financial_params: dict,
) -> dict:
    """
    Build a comprehensive Profit & Loss statement.

    Args:
        sales_detail_df: Order-level revenue data.
        sales_df:        Line-item sales with categories.
        waste_df:        Waste / shrinkage records.
        financial_params: dict with fixed_cost, material_ratio, opex_ratio.

    Returns:
        dict with revenue, cogs, gross_profit, gross_margin, opex,
        fixed_cost, waste, operating_profit, operating_margin, net_profit, net_margin
    """
    amount_col = "amount" if "amount" in sales_detail_df.columns else "revenue"
    revenue = float(sales_detail_df[amount_col].sum())
    material_ratio = financial_params.get("material_ratio", 0.40)
    opex_ratio = financial_params.get("opex_ratio", 0.044)
    fixed_cost = financial_params.get("fixed_cost", 1500)

    # Category-level COGS
    s = sales_df.copy()
    s["cost_ratio"] = s.get("category", pd.Series(dtype=str)).map(CATEGORY_COST_RATIOS).fillna(CATEGORY_COST_RATIOS["default"])
    price_col = "total_price" if "total_price" in s.columns else "amount"
    s["cogs"] = s[price_col] * s["cost_ratio"]
    material_cost = float(s["cogs"].sum())

    gross_profit = revenue - material_cost
    gross_margin = (gross_profit / revenue * 100) if revenue > 0 else 0

    opex_cost = revenue * opex_ratio
    operating_profit = gross_profit - opex_cost - fixed_cost
    operating_margin = (operating_profit / revenue * 100) if revenue > 0 else 0

    # Waste (exclude samples)
    w = waste_df.copy()
    note_col = "note" if "note" in w.columns else w.columns[-1] if not w.empty else "note"
    w[note_col] = w.get(note_col, pd.Series(dtype=str)).fillna("")
    waste_amt_col = "waste_amount" if "waste_amount" in w.columns else "amount"
    mask = ~w[note_col].str.contains("sample", case=False, na=False)
    waste_cost = float(w.loc[mask, waste_amt_col].sum()) if not w.empty else 0

    net_profit = operating_profit - waste_cost
    net_margin = (net_profit / revenue * 100) if revenue > 0 else 0

    return {
        "revenue": round(revenue, 0),
        "cogs": round(material_cost, 0),
        "gross_profit": round(gross_profit, 0),
        "gross_margin_pct": round(gross_margin, 1),
        "opex": round(opex_cost, 0),
        "fixed_cost": round(fixed_cost, 0),
        "waste_loss": round(waste_cost, 0),
        "operating_profit": round(operating_profit, 0),
        "operating_margin_pct": round(operating_margin, 1),
        "net_profit": round(net_profit, 0),
        "net_margin_pct": round(net_margin, 1),
    }


def category_profit_analysis(sales_df: pd.DataFrame) -> pd.DataFrame:
    """
    Profitability breakdown by product category.

    Returns:
        DataFrame with category, revenue, qty, products, cost_ratio,
        cogs, gross_profit, gross_margin_pct, revenue_share_pct
    """
    df = sales_df.copy()
    amount_col = "amount" if "amount" in df.columns else "revenue"
    qty_col = "qty" if "qty" in df.columns else "quantity"
    product_col = "product" if "product" in df.columns else "item"

    cat = df.groupby("category").agg(
        revenue=(amount_col, "sum"),
        qty=(qty_col, "sum") if qty_col in df.columns else (amount_col, "count"),
        products=(product_col, "nunique") if product_col in df.columns else (amount_col, "count"),
    ).reset_index()

    cat["cost_ratio"] = cat["category"].map(CATEGORY_COST_RATIOS).fillna(CATEGORY_COST_RATIOS["default"])
    cat["cogs"] = cat["revenue"] * cat["cost_ratio"]
    cat["gross_profit"] = cat["revenue"] - cat["cogs"]
    cat["gross_margin_pct"] = (cat["gross_profit"] / cat["revenue"] * 100).round(1)
    cat["revenue_share_pct"] = (cat["revenue"] / cat["revenue"].sum() * 100).round(1)

    return cat.sort_values("gross_profit", ascending=False)
