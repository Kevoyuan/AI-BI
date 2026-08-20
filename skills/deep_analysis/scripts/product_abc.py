"""商品 ABC 结构分析与滞销淘汰诊断 (Product ABC & Slow Mover Analysis)。

基于 PosPal 销售流水（按商品名称聚合），计算：
1. 各商品的总实收金额、销量、累计营收占比；
2. 自动划分为 A类核心爆款(前70%)、B类腰部主力(70%~90%)、C类长尾(90%~100%)；
3. 识别处于 C类中销量/金额极低的滞销商品 (Slow Movers)，给出下架或改良建议。
"""

from __future__ import annotations

from typing import Any, Dict, List
import pandas as pd


def analyze_product_abc(
    sales_df: pd.DataFrame,
    top_a_pct: float = 0.70,
    top_b_pct: float = 0.90,
    slow_mover_limit: int = 10,
) -> Dict[str, Any]:
    """计算商品 ABC 分类与滞销商品列表。

    Args:
        sales_df: 包含 ['商品名称', '实收金额', '销售数量'] 的销售流水表。
        top_a_pct: A类累计营收阈值 (默认 70%)。
        top_b_pct: B类累计营收阈值 (默认 90%)。
        slow_mover_limit: 返回滞销商品数量上限。

    Returns:
        结构化分析字典。
    """
    if sales_df.empty or "商品名称" not in sales_df.columns:
        return {
            "error": "销售数据为空或缺少商品名称",
            "total_products": 0,
            "total_revenue": 0.0,
            "abc_summary": {},
            "slow_movers": [],
        }

    df = sales_df.copy()
    df["商品名称"] = df["商品名称"].astype(str).str.strip()
    df = df[~df["商品名称"].isin(["", "nan", "None", "合计", "总计"])]
    df["实收金额"] = pd.to_numeric(df.get("实收金额", 0), errors="coerce").fillna(0)
    df["销售数量"] = pd.to_numeric(df.get("销售数量", 1), errors="coerce").fillna(1)

    # 聚合到单品维度
    prod_group = df.groupby("商品名称").agg(
        total_revenue=("实收金额", "sum"),
        total_quantity=("销售数量", "sum"),
        order_count=("商品名称", "count"),
    ).reset_index()

    total_revenue = float(prod_group["total_revenue"].sum())
    total_products = len(prod_group)

    if total_revenue <= 0 or total_products == 0:
        return {
            "error": "有效销售额为 0",
            "total_products": total_products,
            "total_revenue": 0.0,
            "abc_summary": {},
            "slow_movers": [],
        }

    # 按实收金额降序排序
    prod_group = prod_group.sort_values(by="total_revenue", ascending=False).reset_index(drop=True)
    prod_group["cum_revenue"] = prod_group["total_revenue"].cumsum()
    prod_group["cum_pct"] = prod_group["cum_revenue"] / total_revenue

    # 划分 ABC
    def _classify_abc(cum_pct: float) -> str:
        if cum_pct <= top_a_pct:
            return "A"
        elif cum_pct <= top_b_pct:
            return "B"
        else:
            return "C"

    prod_group["category_abc"] = prod_group["cum_pct"].apply(_classify_abc)

    # 汇总各分类
    a_df = prod_group[prod_group["category_abc"] == "A"]
    b_df = prod_group[prod_group["category_abc"] == "B"]
    c_df = prod_group[prod_group["category_abc"] == "C"]

    # 格式化单品列表
    def _format_items(sub_df: pd.DataFrame, limit: int = 10) -> List[Dict[str, Any]]:
        records = []
        for _, row in sub_df.head(limit).iterrows():
            rev = float(row["total_revenue"])
            share = round((rev / total_revenue) * 100, 1)
            records.append({
                "name": str(row["商品名称"]),
                "revenue": round(rev, 2),
                "quantity": int(row["total_quantity"]),
                "share": f"{share}%",
            })
        return records

    # 滞销品筛选：C 类中金额/销量处于末尾的商品
    slow_df = c_df.sort_values(by=["total_revenue", "total_quantity"], ascending=[True, True])
    slow_movers = _format_items(slow_df, limit=slow_mover_limit)

    abc_summary = {
        "A": {
            "label": "A类 (核心爆款, 前70%营收)",
            "product_count": len(a_df),
            "product_ratio": f"{round(len(a_df)/total_products*100, 1)}%",
            "revenue": round(float(a_df["total_revenue"].sum()), 2),
            "top_products": _format_items(a_df, limit=8),
        },
        "B": {
            "label": "B类 (腰部主力, 70%~90%营收)",
            "product_count": len(b_df),
            "product_ratio": f"{round(len(b_df)/total_products*100, 1)}%",
            "revenue": round(float(b_df["total_revenue"].sum()), 2),
            "top_products": _format_items(b_df, limit=5),
        },
        "C": {
            "label": "C类 (长尾与淘汰候选, 后10%营收)",
            "product_count": len(c_df),
            "product_ratio": f"{round(len(c_df)/total_products*100, 1)}%",
            "revenue": round(float(c_df["total_revenue"].sum()), 2),
        },
    }

    return {
        "total_products": total_products,
        "total_revenue": round(total_revenue, 2),
        "abc_summary": abc_summary,
        "slow_movers": slow_movers,
    }
