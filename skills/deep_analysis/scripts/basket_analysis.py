"""购物篮连带与关联商品分析 (Market Basket Analysis)。

基于 PosPal 的销售流水（按流水号分组），计算：
1. 整体连带率（总件数 / 交易单数）与多件订单占比；
2. 两两商品共购频次、支持度 (Support)、置信度 (Confidence)、提升度 (Lift)；
3. 支持针对特定核心单品（如生吐司、牛角）的定向连带搭配分析。
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Optional
import pandas as pd


def analyze_basket_cross_sell(
    sales_df: pd.DataFrame,
    target_product: Optional[str] = None,
    min_support_count: int = 3,
    top_n: int = 10,
) -> Dict[str, Any]:
    """分析商品连带销售与关联篮子。

    Args:
        sales_df: 包含 ['流水号', '商品名称', '销售数量', '实收金额'] 的销售明细表。
        target_product: 可选，指定某商品名称，查询与该商品最常同时购买的组合。
        min_support_count: 最小共购次数阈值，过滤偶然共购。
        top_n: 返回关联规则/组合数量。

    Returns:
        结构化分析字典。
    """
    if sales_df.empty or "流水号" not in sales_df.columns or "商品名称" not in sales_df.columns:
        return {
            "error": "销售数据为空或缺少流水号/商品名称字段",
            "total_transactions": 0,
            "attachment_rate": 0.0,
            "top_pairs": [],
        }

    # 剔除无效商品名称或汇总行
    df = sales_df.copy()
    df = df[df["流水号"].notna() & df["商品名称"].notna()]
    df["商品名称"] = df["商品名称"].astype(str).str.strip()
    df = df[~df["商品名称"].isin(["", "nan", "None", "合计", "总计"])]
    if "销售数量" in df.columns:
        df["销售数量"] = pd.to_numeric(df["销售数量"], errors="coerce").fillna(1)
    else:
        df["销售数量"] = 1

    # 1. 基础指标：单据数与连带率
    ticket_group = df.groupby("流水号")
    total_tickets = int(ticket_group.ngroups)
    if total_tickets == 0:
        return {
            "error": "有效订单数为 0",
            "total_transactions": 0,
            "attachment_rate": 0.0,
            "top_pairs": [],
        }

    ticket_item_counts = ticket_group["销售数量"].sum()
    total_items = float(ticket_item_counts.sum())
    attachment_rate = round(total_items / total_tickets, 2)  # 平均连带率
    multi_item_tickets = int((ticket_item_counts > 1).sum())
    multi_item_ratio = round((multi_item_tickets / total_tickets) * 100, 1)  # 多件单占比%

    # 2. 每个单据包含的去重商品集合
    baskets = ticket_group["商品名称"].apply(lambda s: set(s)).tolist()

    # 单品出现频次
    item_counts: Dict[str, int] = {}
    pair_counts: Dict[tuple, int] = {}

    for b in baskets:
        # 单品计数
        for item in b:
            item_counts[item] = item_counts.get(item, 0) + 1
        # 两两组合计数（字典序排好元组）
        if len(b) >= 2:
            for item1, item2 in combinations(sorted(b), 2):
                pair_counts[(item1, item2)] = pair_counts.get((item1, item2), 0) + 1

    # 3. 组合分析与过滤
    pairs_list: List[Dict[str, Any]] = []

    if target_product:
        target_norm = target_product.strip()
        # 模糊匹配找到最接近的单品全称
        matched_items = [it for it in item_counts if target_norm in it]
        if not matched_items:
            # 没有找到商品
            return {
                "total_transactions": total_tickets,
                "attachment_rate": attachment_rate,
                "multi_item_ratio": f"{multi_item_ratio}%",
                "target_product": target_product,
                "message": f"未在历史销售记录中找到与 '{target_product}' 匹配的商品",
                "top_pairs": [],
            }
        
        target_exact = matched_items[0]
        target_freq = item_counts[target_exact]

        for (item1, item2), count in pair_counts.items():
            if target_exact in (item1, item2) and count >= min_support_count:
                other_item = item2 if item1 == target_exact else item1
                other_freq = item_counts[other_item]
                # 置信度：买了 target 时，同时也买 other 的概率
                confidence = round((count / target_freq) * 100, 1)
                # 提升度 Lift = P(A & B) / (P(A) * P(B))
                lift = round((count * total_tickets) / (target_freq * other_freq), 2)
                pairs_list.append({
                    "item_a": target_exact,
                    "item_b": other_item,
                    "co_occurrence": count,
                    "confidence": f"{confidence}%",
                    "lift": lift,
                })
        
        # 按共购频次及置信度降序
        pairs_list.sort(key=lambda x: (x["co_occurrence"], x["lift"]), reverse=True)

        return {
            "total_transactions": total_tickets,
            "attachment_rate": attachment_rate,
            "multi_item_ratio": f"{multi_item_ratio}%",
            "target_product": target_exact,
            "target_sales_count": target_freq,
            "top_pairs": pairs_list[:top_n],
        }

    # 全局高频组合
    for (item1, item2), count in pair_counts.items():
        if count >= min_support_count:
            freq1 = item_counts[item1]
            freq2 = item_counts[item2]
            # 置信度 A -> B
            conf_a_to_b = round((count / freq1) * 100, 1)
            lift = round((count * total_tickets) / (freq1 * freq2), 2)
            pairs_list.append({
                "item_a": item1,
                "item_b": item2,
                "co_occurrence": count,
                "confidence_a_to_b": f"{conf_a_to_b}%",
                "lift": lift,
            })

    pairs_list.sort(key=lambda x: (x["co_occurrence"], x["lift"]), reverse=True)

    return {
        "total_transactions": total_tickets,
        "attachment_rate": attachment_rate,
        "multi_item_ratio": f"{multi_item_ratio}%",
        "top_pairs": pairs_list[:top_n],
    }
