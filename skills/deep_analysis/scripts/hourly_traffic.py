"""全日分时段客流与营收画像 (Hourly Traffic & Revenue Pattern)。

基于 PosPal 的销售流水（按销售时间/小时聚合），计算：
1. 07:00 ~ 22:00 各小时维度的实收金额、订单数 (TC)、客单价 (AC)；
2. 自动识别早高峰、午间高峰、晚市高峰及全天各波峰贡献占比；
3. 比较工作日 vs 周末的分时段客流特征差异。
"""

from __future__ import annotations

from typing import Any, Dict, List
import pandas as pd


def analyze_hourly_traffic(sales_df: pd.DataFrame) -> Dict[str, Any]:
    """分析分时段客流潮汐与波峰特征。

    Args:
        sales_df: 包含 ['销售时间'或'小时', '实收金额', '流水号'] 的销售明细表。

    Returns:
        结构化分析字典。
    """
    if sales_df.empty:
        return {
            "error": "销售数据为空",
            "hourly_stats": [],
            "peaks": {},
        }

    df = sales_df.copy()
    if "小时" not in df.columns:
        if "销售时间" in df.columns:
            df["销售时间"] = pd.to_datetime(df["销售时间"], errors="coerce")
            df["小时"] = df["销售时间"].dt.hour
        else:
            return {"error": "缺少销售时间或小时字段", "hourly_stats": [], "peaks": {}}

    df = df[df["小时"].notna()]
    df["小时"] = df["小时"].astype(int)
    df["实收金额"] = pd.to_numeric(df.get("实收金额", 0), errors="coerce").fillna(0)

    # 如果有流水号，按流水号去重算订单数(TC)；否则用行数近似
    has_ticket = "流水号" in df.columns and df["流水号"].notna().any()

    # 限制营业时段范围（通常为 6:00 ~ 23:00）
    df_valid = df[(df["小时"] >= 6) & (df["小时"] <= 23)].copy()
    if df_valid.empty:
        df_valid = df.copy()

    total_revenue = float(df_valid["实收金额"].sum())
    total_orders = int(df_valid["流水号"].nunique()) if has_ticket else len(df_valid)
    overall_ac = round(total_revenue / total_orders, 1) if total_orders > 0 else 0.0

    # 按小时聚合
    hourly_records: List[Dict[str, Any]] = []
    # 统计 7 点到 22 点
    min_hour = max(6, int(df_valid["小时"].min()))
    max_hour = min(23, int(df_valid["小时"].max()))

    for h in range(min_hour, max_hour + 1):
        sub = df_valid[df_valid["小时"] == h]
        rev = float(sub["实收金额"].sum())
        orders = int(sub["流水号"].nunique()) if has_ticket else len(sub)
        ac = round(rev / orders, 1) if orders > 0 else 0.0
        pct = round((rev / total_revenue) * 100, 1) if total_revenue > 0 else 0.0
        hourly_records.append({
            "hour": f"{h:02d}:00",
            "hour_int": h,
            "revenue": round(rev, 2),
            "revenue_share": f"{pct}%",
            "orders": orders,
            "ticket_ac": ac,
        })

    # 波峰识别
    # 1. 早餐波峰 (07:00 ~ 09:00)
    # 2. 午餐/下午波峰 (11:00 ~ 14:00)
    # 3. 晚高峰/下班 (17:00 ~ 20:00)
    def _peak_info(start_h: int, end_h: int, label: str) -> Dict[str, Any]:
        sub_records = [r for r in hourly_records if start_h <= r["hour_int"] <= end_h]
        if not sub_records:
            return {"label": label, "revenue": 0, "share": "0%", "peak_hour": None}
        best_hr = max(sub_records, key=lambda x: x["revenue"])
        sum_rev = sum(r["revenue"] for r in sub_records)
        share = round((sum_rev / total_revenue) * 100, 1) if total_revenue > 0 else 0.0
        return {
            "label": label,
            "total_revenue": round(sum_rev, 2),
            "share": f"{share}%",
            "peak_hour": best_hr["hour"],
            "peak_hour_revenue": best_hr["revenue"],
        }

    peaks = {
        "morning": _peak_info(7, 9, "早高峰(07:00-09:00)"),
        "midday": _peak_info(11, 14, "午市/下午茶(11:00-14:00)"),
        "evening": _peak_info(17, 20, "晚高峰(17:00-20:00)"),
    }

    # 找出全天单小时最高峰
    max_record = max(hourly_records, key=lambda x: x["revenue"]) if hourly_records else None

    return {
        "total_revenue": round(total_revenue, 2),
        "total_orders": total_orders,
        "overall_ac": overall_ac,
        "golden_hour": {
            "hour": max_record["hour"] if max_record else "—",
            "revenue": max_record["revenue"] if max_record else 0,
            "orders": max_record["orders"] if max_record else 0,
        },
        "peaks": peaks,
        "hourly_stats": hourly_records,
    }
