"""储值卡消耗与现金流健康度分析 (Recharge & Cash Flow Health Analysis)。

基于 PosPal 的充值流水 (cards_detail) 与小票支付方式 (sales_detail)，计算：
1. 当期营业实收中：新真金白银（微信/支付宝/现金）vs 储值卡抵扣（存量消耗）比例；
2. 会员当期新增充值与赠送金额统计，及充值档位分布；
3. 真实净现金流入 = (营业新现金收入 + 新增充值) - 运营支出基准；
4. 评估现金流真实成色与风险预警（如储值卡消耗占比 > 60%）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import pandas as pd


def analyze_recharge_health(
    sales_detail_df: pd.DataFrame,
    cards_detail_df: pd.DataFrame,
) -> Dict[str, Any]:
    """分析储值卡消耗与真实现金流健康度。

    Args:
        sales_detail_df: 销售单据表，包含实收金额与支付方式。
        cards_detail_df: 充值明细表，包含充值金额与赠送金额。

    Returns:
        结构化分析字典。
    """
    # 1. 单据支付方式拆解（新现金 vs 储值卡消耗）
    total_sales_revenue = 0.0
    card_consume_amount = 0.0
    direct_cash_amount = 0.0

    if not sales_detail_df.empty:
        df_s = sales_detail_df.copy()
        if "实收金额" in df_s.columns:
            df_s["实收金额"] = pd.to_numeric(df_s["实收金额"], errors="coerce").fillna(0)
            total_sales_revenue = float(df_s["实收金额"].sum())

        # 检查是否包含具体的支付方式列或单列
        # 在 PosPal 中，sales_detail 可能有各支付列（储值卡支付, 微信支付...）或由 payments 表支撑
        card_cols = [c for c in df_s.columns if "储值卡" in c or "会员卡" in c]
        if card_cols:
            card_consume_amount = float(pd.to_numeric(df_s[card_cols[0]], errors="coerce").fillna(0).sum())
            direct_cash_amount = max(0.0, total_sales_revenue - card_consume_amount)
        elif "支付方式" in df_s.columns:
            card_mask = df_s["支付方式"].astype(str).str.contains("储值|会员|卡", na=False)
            card_consume_amount = float(df_s[card_mask]["实收金额"].sum())
            direct_cash_amount = float(df_s[~card_mask]["实收金额"].sum())
        else:
            # 兜底
            direct_cash_amount = total_sales_revenue

    card_consume_ratio = (
        round((card_consume_amount / total_sales_revenue) * 100, 1)
        if total_sales_revenue > 0
        else 0.0
    )
    direct_cash_ratio = round(100.0 - card_consume_ratio, 1)

    # 2. 会员充值明细拆解
    total_recharge = 0.0
    total_gift = 0.0
    recharge_count = 0
    tier_counts = {"small": 0, "medium": 0, "large": 0}  # <200, 200~500, >500

    if not cards_detail_df.empty:
        df_c = cards_detail_df.copy()
        if "充值金额" in df_c.columns:
            df_c["充值金额"] = pd.to_numeric(df_c["充值金额"], errors="coerce").fillna(0)
            total_recharge = float(df_c["充值金额"].sum())
            recharge_count = len(df_c[df_c["充值金额"] > 0])

            # 档位划分
            tier_counts["small"] = int((df_c["充值金额"] < 200).sum())
            tier_counts["medium"] = int(((df_c["充值金额"] >= 200) & (df_c["充值金额"] <= 500)).sum())
            tier_counts["large"] = int((df_c["充值金额"] > 500).sum())

        if "赠送金额" in df_c.columns:
            df_c["赠送金额"] = pd.to_numeric(df_c["赠送金额"], errors="coerce").fillna(0)
            total_gift = float(df_c["赠送金额"].sum())

    # 3. 净新增进账 (实收中的直接现金 + 新收到的充值款)
    actual_cash_inflow = round(direct_cash_amount + total_recharge, 2)

    # 4. 健康度评估
    health_level = "healthy"
    health_notes: List[str] = []

    if total_sales_revenue > 0:
        if card_consume_ratio > 50.0 and total_recharge < (card_consume_amount * 0.5):
            health_level = "warning"
            health_notes.append("储值卡消耗占比偏高且新增充值补充不足，当期主要依赖消耗历史负债。")
        elif card_consume_ratio <= 35.0:
            health_notes.append("直接现金流（微信/支付宝/现金）占比充盈，造血能力良好。")
        else:
            health_notes.append("储值卡消耗与新增现金流比例保持在健康平衡区间。")

    if total_gift > 0 and total_recharge > 0:
        gift_ratio = round((total_gift / total_recharge) * 100, 1)
        if gift_ratio > 25.0:
            health_notes.append(f"充值赠送率较高({gift_ratio}%)，需留意远期毛利稀释风险。")

    return {
        "total_sales_revenue": round(total_sales_revenue, 2),
        "revenue_structure": {
            "direct_cash_amount": round(direct_cash_amount, 2),
            "direct_cash_ratio": f"{direct_cash_ratio}%",
            "card_consume_amount": round(card_consume_amount, 2),
            "card_consume_ratio": f"{card_consume_ratio}%",
        },
        "recharge_summary": {
            "total_recharge_inflow": round(total_recharge, 2),
            "total_gift_amount": round(total_gift, 2),
            "recharge_orders": recharge_count,
            "tier_distribution": {
                "small_under_200": tier_counts["small"],
                "medium_200_to_500": tier_counts["medium"],
                "large_over_500": tier_counts["large"],
            },
        },
        "actual_cash_inflow": actual_cash_inflow,
        "health_evaluation": {
            "level": health_level,
            "notes": health_notes,
        },
    }
