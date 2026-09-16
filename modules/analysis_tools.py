"""Parameterized analysis tools for the AI assistant.

Wraps the legacy pure-pandas analysis functions (skills/forecast_alert/scripts/)
and feeds them data from the current dashboard data layer (pospal_live_data +
weather_api). Schema drift introduced since those scripts were written is fixed
here in the adapter — the legacy scripts stay untouched.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

MAX_WINDOW_DAYS = 90


# --------------------------------------------------------------------------- #
# Window resolution (same date_spec contract as fetch_pospal_data)
# --------------------------------------------------------------------------- #
def resolve_window(date_spec: Any, default_days: int = 30) -> Tuple[date, date]:
    """Return ``(start, end)`` from a date_spec string, dict, or DashboardQuery."""
    from modules.dashboard_api import DashboardQuery

    today = date.today()

    if isinstance(date_spec, DashboardQuery):
        if date_spec.date_from and date_spec.date_to:
            start = date.fromisoformat(date_spec.date_from)
            end = date.fromisoformat(date_spec.date_to)
        else:
            y, m = date_spec.year, date_spec.month
            start = date(y, m, 1)
            end = _month_end(y, m)
        return (end, start) if start > end else (start, end)

    if isinstance(date_spec, str):
        s = date_spec.strip()
        if s == "today":
            return today, today
        if s == "yesterday":
            y = today - timedelta(days=1)
            return y, y
        if s == "week":
            start = today - timedelta(days=today.weekday())
            return start, start + timedelta(days=6)
        if s == "month":
            return today.replace(day=1), today

        m = re.match(r"^(\d{4})[-/年](\d{1,2})月?$", s)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            return date(y, mo, 1), _month_end(y, mo)

        m = re.match(r"^(\d{1,2})月$", s)
        if m:
            mo = int(m.group(1))
            return date(today.year, mo, 1), _month_end(today.year, mo)

        m = re.match(
            r"^(\d{4})[-/年](\d{1,2})月?\s*(?:[~至到,]|to)\s*(\d{4})[-/年](\d{1,2})月?$",
            s,
        )
        if m:
            y1, m1, y2, m2 = map(int, m.groups())
            start, end = date(y1, m1, 1), _month_end(y2, m2)
            return (end, start) if start > end else (start, end)

        m = re.match(
            r"^(\d{4}-\d{2}-\d{2})\s*(?:[~至到,]|to)\s*(\d{4}-\d{2}-\d{2})$",
            s,
        )
        if m:
            start, end = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
            return (end, start) if start > end else (start, end)

        m = re.match(r"^(\d{4}-\d{2}-\d{2})$", s)
        if m:
            d = date.fromisoformat(m.group(1))
            return d, d

    if isinstance(date_spec, dict) and "preset" in date_spec:
        preset = str(date_spec["preset"])
        if preset == "today":
            return today, today
        if preset == "yesterday":
            y = today - timedelta(days=1)
            return y, y
        if preset == "week":
            start = today - timedelta(days=today.weekday())
            return start, start + timedelta(days=6)
        return today.replace(day=1), today

    if isinstance(date_spec, dict) and "year" in date_spec and "month" in date_spec:
        y, m = int(date_spec["year"]), int(date_spec["month"])
        return date(y, m, 1), _month_end(y, m)

    if isinstance(date_spec, dict) and (
        date_spec.get("date_from") or date_spec.get("date_to")
    ):
        df, dt = date_spec.get("date_from"), date_spec.get("date_to")
        start = date.fromisoformat(df) if df else today
        end = date.fromisoformat(dt) if dt else today
        return (end, start) if start > end else (start, end)

    start = today - timedelta(days=default_days)
    if (today - start).days > MAX_WINDOW_DAYS:
        start = today - timedelta(days=MAX_WINDOW_DAYS)
    return start, today


def _month_end(year: int, month: int) -> date:
    end = date(year, month, 28)
    while end.month == month:
        end += timedelta(days=1)
    return end - timedelta(days=1)


def _month_span(start: date, end: date) -> List[Tuple[int, int]]:
    months: List[Tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


# --------------------------------------------------------------------------- #
# Data access (reuses the cached PosPal + weather layers with a micro-cache)
# --------------------------------------------------------------------------- #
_ANALYSIS_WINDOW_CACHE: Dict[str, Tuple[float, Any]] = {}
ANALYSIS_WINDOW_CACHE_TTL_SECONDS = 300


def clear_analysis_cache() -> None:
    """Clear the short-lived analysis data cache (primarily for tests)."""
    _ANALYSIS_WINDOW_CACHE.clear()


def _get_window_cache(key: str) -> Any | None:
    item = _ANALYSIS_WINDOW_CACHE.get(key)
    if item is None:
        return None
    cached_time, value = item
    if time.time() - cached_time > ANALYSIS_WINDOW_CACHE_TTL_SECONDS:
        _ANALYSIS_WINDOW_CACHE.pop(key, None)
        return None
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, tuple):
        return tuple(v.copy() if isinstance(v, pd.DataFrame) else v for v in value)
    return value


def _set_window_cache(key: str, value: Any) -> None:
    if len(_ANALYSIS_WINDOW_CACHE) >= 64:
        oldest = min(_ANALYSIS_WINDOW_CACHE, key=lambda k: _ANALYSIS_WINDOW_CACHE[k][0])
        _ANALYSIS_WINDOW_CACHE.pop(oldest, None)
    _ANALYSIS_WINDOW_CACHE[key] = (time.time(), value)


def _fetch_sales_window(start: date, end: date) -> pd.DataFrame:
    cache_key = f"sales_win:{start}:{end}"
    cached = _get_window_cache(cache_key)
    if cached is not None:
        return cached

    from modules.pospal_live_data import fetch_live_pospal_data

    frames: List[pd.DataFrame] = []
    for year, month in _month_span(start, end):
        live = fetch_live_pospal_data(year, month)
        sales = live.sales
        if sales is None or sales.empty:
            continue
        df = sales[["销售时间", "实收金额"]].copy()
        df["日期"] = pd.to_datetime(df["销售时间"], errors="coerce").dt.date
        df["实收金额"] = pd.to_numeric(df["实收金额"], errors="coerce").fillna(0)
        frames.append(df[df["日期"].notna()][["日期", "实收金额"]])
    if not frames:
        result = pd.DataFrame(columns=["日期", "实收金额"])
        _set_window_cache(cache_key, result)
        return result
    out = pd.concat(frames, ignore_index=True)
    out["日期"] = pd.to_datetime(out["日期"])
    mask = (out["日期"].dt.date >= start) & (out["日期"].dt.date <= end)
    result = out[mask]
    _set_window_cache(cache_key, result)
    return result.copy()


def _fetch_sales_full_window(start: date, end: date) -> pd.DataFrame:
    cache_key = f"sales_full:{start}:{end}"
    cached = _get_window_cache(cache_key)
    if cached is not None:
        return cached

    from modules.pospal_live_data import fetch_live_pospal_data

    frames: List[pd.DataFrame] = []
    for year, month in _month_span(start, end):
        live = fetch_live_pospal_data(year, month)
        sales = live.sales
        if sales is None or sales.empty:
            continue
        cols = [
            c
            for c in [
                "流水号",
                "商品名称",
                "商品条码",
                "销售时间",
                "小时",
                "销售数量",
                "实收金额",
                "商品原价",
                "成本",
                "利润",
                "商品分类",
            ]
            if c in sales.columns
        ]
        df = sales[cols].copy()
        df["日期"] = pd.to_datetime(df.get("销售时间"), errors="coerce").dt.date
        frames.append(df[df["日期"].notna()])
    if not frames:
        result = pd.DataFrame()
        _set_window_cache(cache_key, result)
        return result
    out = pd.concat(frames, ignore_index=True)
    mask = (out["日期"] >= start) & (out["日期"] <= end)
    result = out[mask]
    _set_window_cache(cache_key, result)
    return result.copy()


def _fetch_loss_full_window(start: date, end: date) -> pd.DataFrame:
    cache_key = f"loss_full:{start}:{end}"
    cached = _get_window_cache(cache_key)
    if cached is not None:
        return cached

    from modules.pospal_live_data import fetch_live_pospal_data

    frames: List[pd.DataFrame] = []
    for year, month in _month_span(start, end):
        live = fetch_live_pospal_data(year, month)
        loss = live.loss
        if loss is None or loss.empty:
            continue
        cols = [
            c
            for c in [
                "序号",
                "报损时间",
                "调整日期",
                "审核时间",
                "商品分类",
                "商品名称",
                "条码",
                "商品条码",
                "报废数量",
                "数量",
                "报损金额",
                "金额",
                "报损原因",
                "备注",
            ]
            if c in loss.columns
        ]
        df = loss[cols].copy()
        if "调整日期" in df.columns:
            df["日期"] = pd.to_datetime(df["调整日期"], errors="coerce").dt.date
        elif "审核时间" in df.columns:
            df["日期"] = pd.to_datetime(df["审核时间"], errors="coerce").dt.date
        elif "报损时间" in df.columns:
            df["日期"] = pd.to_datetime(df["报损时间"], errors="coerce").dt.date
        else:
            continue
        frames.append(df[df["日期"].notna()])
    if not frames:
        result = pd.DataFrame()
        _set_window_cache(cache_key, result)
        return result
    out = pd.concat(frames, ignore_index=True)
    mask = (out["日期"] >= start) & (out["日期"] <= end)
    result = out[mask]
    _set_window_cache(cache_key, result)
    return result.copy()


def _fetch_weather_window(start: date, end: date) -> pd.DataFrame:
    cache_key = f"weather_win:{start}:{end}"
    cached = _get_window_cache(cache_key)
    if cached is not None:
        return cached

    from modules.weather_api import fetch_humen_daily_weather

    fetched = fetch_humen_daily_weather(start, end)
    result = fetched.data if fetched.data is not None else pd.DataFrame()
    _set_window_cache(cache_key, result)
    return result.copy()


def _normalize_weather(df_w: pd.DataFrame) -> pd.DataFrame:
    if df_w.empty or "天气" not in df_w.columns:
        return df_w
    df = df_w.copy()
    df["天气"] = df["天气"].map(
        {"晴": "晴天", "大致晴朗": "晴天", "多云": "多云", "阴": "阴天"}
    ).fillna(df["天气"])
    return df


# --------------------------------------------------------------------------- #
# Analysis entry points
# --------------------------------------------------------------------------- #
def run_forecast(date_spec: Any, horizon: str = "tomorrow") -> Dict[str, Any]:
    if horizon not in ("tomorrow", "next_week"):
        raise ValueError("horizon 必须是 tomorrow 或 next_week")
    _start, end = resolve_window(date_spec, default_days=30)
    anchor_date = end
    history_start = anchor_date - timedelta(days=60)
    sales = _fetch_sales_window(history_start, anchor_date)
    if sales.empty:
        return {
            "analysis": "forecast",
            "error": "窗口内无销售数据",
            "窗口": f"{history_start} ~ {anchor_date}",
        }
    sales = sales.copy()
    sales["日期"] = pd.to_datetime(sales["日期"])

    if horizon == "next_week":
        from skills.forecast_alert.scripts.prediction import predict_next_week

        result = predict_next_week(sales)
    else:
        from skills.forecast_alert.scripts.prediction import predict_tomorrow

        result = predict_tomorrow(sales, anchor_date=anchor_date)

    return {
        "analysis": "forecast",
        "horizon": horizon,
        "基准日期": str(anchor_date),
        "历史数据窗口": f"{history_start} ~ {anchor_date}",
        "有效数据天数": int(sales["日期"].dt.date.nunique()),
        "result": result,
    }


def run_weather_impact(date_spec: Any) -> Dict[str, Any]:
    target_start, target_end = resolve_window(date_spec, default_days=30)
    history_start = target_end - timedelta(days=60)
    history_end = target_end

    sales_history = _fetch_sales_window(history_start, history_end)
    if sales_history.empty:
        return {
            "analysis": "weather",
            "error": "窗口内无销售数据",
            "目标窗口": f"{target_start} ~ {target_end}",
            "历史统计窗口": f"{history_start} ~ {history_end}",
        }
    sales_history = sales_history.copy()
    sales_history["日期"] = pd.to_datetime(sales_history["日期"])
    weather_history = _normalize_weather(_fetch_weather_window(history_start, history_end))
    target_weather = _normalize_weather(_fetch_weather_window(target_start, target_end))

    target_weather_list: List[Dict[str, Any]] = []
    target_weather_labels: List[str] = []
    if not target_weather.empty:
        for _, row in target_weather.iterrows():
            item = {
                "日期": str(row.get("日期")),
                "天气": row.get("天气"),
                "最高温": row.get("最高温"),
                "最低温": row.get("最低温"),
                "降水量mm": row.get("降水量mm"),
            }
            target_weather_list.append({k: v for k, v in item.items() if pd.notna(v)})
            if row.get("天气"):
                target_weather_labels.append(str(row.get("天气")))

    from skills.forecast_alert.scripts.weather_impact import weather_alert, weather_impact_summary

    impact = (
        weather_impact_summary(sales_history, weather_history)
        if not weather_history.empty
        else None
    )
    alert = (
        weather_alert(
            weather_history if not weather_history.empty else target_weather,
            sales_history,
        )
        if (not weather_history.empty or not target_weather.empty)
        else {"预警": "无恶劣天气记录", "级别": "🟢 正常"}
    )

    attribution: List[str] = []
    if impact is not None and target_weather_labels:
        impact_map = {
            row.get("天气"): row.get("影响系数%")
            for row in impact.to_dict("records")
            if row.get("天气") and row.get("影响系数%") is not None
        }
        for weather_label in set(target_weather_labels):
            if weather_label in impact_map:
                coeff = impact_map[weather_label]
                direction = "下滑" if coeff < 0 else "提升"
                attribution.append(
                    f"目标日期天气为【{weather_label}】，历史模型显示该天气下日均实收{direction} {abs(coeff):.1f}%"
                )

    impact_records = None if impact is None else impact.to_dict("records")
    return {
        "analysis": "weather",
        "目标窗口": f"{target_start} ~ {target_end}",
        "目标日天气实况": target_weather_list,
        "天气归因诊断": "；".join(attribution)
        if attribution
        else ("目标日天气正常或无历史负向异常" if target_weather_list else "目标日期暂无实况天气数据"),
        "历史统计窗口": f"{history_start} ~ {history_end}",
        "历史天气覆盖天数": int(weather_history["日期"].nunique())
        if ("日期" in weather_history.columns and not weather_history.empty)
        else 0,
        "各天气影响系数": impact_records,
        "影响系数": impact_records,
        "预警": alert,
    }


def run_basket_analysis(
    date_spec: Any = None,
    target_product: str | None = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    start, end = resolve_window(date_spec, default_days=30)
    sales = _fetch_sales_full_window(start, end)
    if sales.empty:
        return {
            "analysis": "basket",
            "error": "窗口内无销售明细数据",
            "窗口": f"{start} ~ {end}",
        }
    from skills.deep_analysis.scripts.basket_analysis import analyze_basket_cross_sell

    result = analyze_basket_cross_sell(sales, target_product=target_product, top_n=top_n)
    result["analysis"] = "basket"
    result["窗口"] = f"{start} ~ {end}"
    return result


def run_hourly_traffic(date_spec: Any = None) -> Dict[str, Any]:
    start, end = resolve_window(date_spec, default_days=30)
    sales = _fetch_sales_full_window(start, end)
    if sales.empty:
        return {
            "analysis": "hourly",
            "error": "窗口内无销售明细数据",
            "窗口": f"{start} ~ {end}",
        }
    from skills.deep_analysis.scripts.hourly_traffic import analyze_hourly_traffic

    result = analyze_hourly_traffic(sales)
    result["analysis"] = "hourly"
    result["窗口"] = f"{start} ~ {end}"
    return result


def run_product_abc(
    date_spec: Any = None,
    top_a_pct: float = 0.70,
    top_b_pct: float = 0.90,
) -> Dict[str, Any]:
    start, end = resolve_window(date_spec, default_days=30)
    sales = _fetch_sales_full_window(start, end)
    if sales.empty:
        return {
            "analysis": "abc",
            "error": "窗口内无销售数据",
            "窗口": f"{start} ~ {end}",
        }
    from skills.deep_analysis.scripts.product_abc import analyze_product_abc

    result = analyze_product_abc(sales, top_a_pct=top_a_pct, top_b_pct=top_b_pct)
    result["analysis"] = "abc"
    result["窗口"] = f"{start} ~ {end}"
    return result


def _fetch_recharge_window(start: date, end: date) -> Tuple[pd.DataFrame, pd.DataFrame]:
    cache_key = f"recharge_win:{start}:{end}"
    cached = _get_window_cache(cache_key)
    if cached is not None and isinstance(cached, tuple) and len(cached) == 2:
        return cached[0].copy(), cached[1].copy()

    from modules.pospal_live_data import fetch_live_pospal_data

    sales_details: List[pd.DataFrame] = []
    cards_details: List[pd.DataFrame] = []
    for year, month in _month_span(start, end):
        live = fetch_live_pospal_data(year, month)
        if live.sales_detail is not None and not live.sales_detail.empty:
            df = live.sales_detail.copy()
            if "日期" in df.columns:
                df["_d"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
                sales_details.append(df[df["_d"].notna()])
            else:
                sales_details.append(df)
        if live.cards_detail is not None and not live.cards_detail.empty:
            df = live.cards_detail.copy()
            if "充值时间" in df.columns:
                df["_d"] = pd.to_datetime(df["充值时间"], errors="coerce").dt.date
                cards_details.append(df[df["_d"].notna()])
            else:
                cards_details.append(df)

    sales_out = pd.concat(sales_details, ignore_index=True) if sales_details else pd.DataFrame()
    cards_out = pd.concat(cards_details, ignore_index=True) if cards_details else pd.DataFrame()
    if not sales_out.empty and "_d" in sales_out.columns:
        sales_out = sales_out[(sales_out["_d"] >= start) & (sales_out["_d"] <= end)].drop(columns=["_d"])
    if not cards_out.empty and "_d" in cards_out.columns:
        cards_out = cards_out[(cards_out["_d"] >= start) & (cards_out["_d"] <= end)].drop(columns=["_d"])
    _set_window_cache(cache_key, (sales_out, cards_out))
    return sales_out.copy(), cards_out.copy()


def run_recharge_health(date_spec: Any = None) -> Dict[str, Any]:
    start, end = resolve_window(date_spec, default_days=30)
    sales_detail, cards_detail = _fetch_recharge_window(start, end)
    if sales_detail.empty and cards_detail.empty:
        return {
            "analysis": "recharge",
            "error": "窗口内无充值与小票单据数据",
            "窗口": f"{start} ~ {end}",
        }
    from skills.profit_cost.scripts.recharge_health import analyze_recharge_health

    result = analyze_recharge_health(sales_detail, cards_detail)
    result["analysis"] = "recharge"
    result["窗口"] = f"{start} ~ {end}"
    return result


def query_product_sales(
    product_name: str,
    date_spec: Any = None,
    by_barcode: bool = True,
) -> Dict[str, Any]:
    """Query a specific product and merge renamed aliases sharing a barcode."""
    query_str = str(product_name or "").strip()
    if not query_str:
        return {"error": "请提供要查询的商品名称"}

    start, end = resolve_window(date_spec, default_days=60)
    sales = _fetch_sales_full_window(start, end)
    if sales.empty or "商品名称" not in sales.columns:
        return {
            "found": False,
            "query": query_str,
            "window": f"{start} ~ {end}",
            "message": f"在时间范围 {start} ~ {end} 内暂无销售流水数据",
        }

    product_names = sales["商品名称"].astype(str).str.strip()
    q_lower = query_str.lower()
    name_mask = product_names.str.lower().str.contains(q_lower, na=False)
    if not name_mask.any():
        unique_names = product_names.unique()
        suggestions = [name for name in unique_names if any(ch in name for ch in query_str)][:5]
        return {
            "found": False,
            "query": query_str,
            "window": f"{start} ~ {end}",
            "message": f"在时间范围 {start} ~ {end} 内未找到名称包含「{query_str}」的商品销售记录",
            "suggestions": suggestions,
        }

    matched_sales = sales[name_mask].copy()
    barcodes: set[str] = set()
    if by_barcode and "商品条码" in matched_sales.columns:
        raw = matched_sales["商品条码"].dropna().astype(str).str.strip().unique()
        barcodes = {b for b in raw if b and b.lower() not in ("nan", "none", "0")}
        if barcodes:
            barcode_mask = sales["商品条码"].astype(str).str.strip().isin(barcodes)
            matched_sales = sales[name_mask | barcode_mask].copy()

    qty = (
        pd.to_numeric(matched_sales["销售数量"], errors="coerce").fillna(0)
        if "销售数量" in matched_sales.columns
        else pd.Series([0])
    )
    revenue = (
        pd.to_numeric(matched_sales["实收金额"], errors="coerce").fillna(0)
        if "实收金额" in matched_sales.columns
        else pd.Series([0.0])
    )
    total_quantity = int(qty.sum())
    total_revenue = round(float(revenue.sum()), 2)
    order_count = (
        int(matched_sales["流水号"].nunique())
        if "流水号" in matched_sales.columns
        else len(matched_sales)
    )
    avg_price = round(total_revenue / total_quantity, 2) if total_quantity else 0.0
    total_profit = None
    if "利润" in matched_sales.columns:
        profits = pd.to_numeric(matched_sales["利润"], errors="coerce").fillna(0)
        total_profit = round(float(profits.sum()), 2)

    matched_sales["_clean_name"] = matched_sales["商品名称"].fillna("未知商品").astype(str).str.strip()
    has_barcode = "商品条码" in matched_sales.columns
    if has_barcode:
        matched_sales["_clean_barcode"] = (
            matched_sales["商品条码"]
            .fillna("无条码")
            .astype(str)
            .str.strip()
            .replace({"": "无条码", "nan": "无条码", "None": "无条码"})
        )
        group_cols = ["_clean_name", "_clean_barcode"]
    else:
        matched_sales["_clean_barcode"] = "无条码"
        group_cols = ["_clean_name"]

    name_breakdown: List[Dict[str, Any]] = []
    for key, group in matched_sales.groupby(group_cols):
        if has_barcode and isinstance(key, tuple):
            group_name, group_barcode = key
        else:
            group_name, group_barcode = key, "无条码"
        group_qty = int(pd.to_numeric(group.get("销售数量", 0), errors="coerce").fillna(0).sum())
        group_revenue = round(float(pd.to_numeric(group.get("实收金额", 0), errors="coerce").fillna(0).sum()), 2)
        group_orders = int(group["流水号"].nunique()) if "流水号" in group.columns else len(group)
        dates = pd.to_datetime(group["日期"], errors="coerce").dropna().dt.date
        name_breakdown.append(
            {
                "name": str(group_name).strip(),
                "barcode": str(group_barcode).strip(),
                "quantity": group_qty,
                "revenue": group_revenue,
                "orders": group_orders,
                "first_sold": str(dates.min()) if not dates.empty else "",
                "last_sold": str(dates.max()) if not dates.empty else "",
            }
        )
    name_breakdown.sort(key=lambda item: item["quantity"], reverse=True)

    unique_names = list(matched_sales["_clean_name"].unique())
    has_name_alias = len(unique_names) > 1

    matched_sales["_month"] = pd.to_datetime(matched_sales["日期"], errors="coerce").dt.strftime("%Y-%m")
    monthly_breakdown: List[Dict[str, Any]] = []
    for month, group in matched_sales.groupby("_month"):
        if pd.isna(month):
            continue
        monthly_breakdown.append(
            {
                "month": str(month),
                "quantity": int(pd.to_numeric(group.get("销售数量", 0), errors="coerce").fillna(0).sum()),
                "revenue": round(float(pd.to_numeric(group.get("实收金额", 0), errors="coerce").fillna(0).sum()), 2),
                "days_sold": int(group["日期"].nunique()),
                "names": list(group["_clean_name"].unique()),
            }
        )
    monthly_breakdown.sort(key=lambda item: item["month"])

    loss_summary: Dict[str, Any] = {"total_quantity": 0, "total_amount": 0.0, "reasons": []}
    loss = _fetch_loss_full_window(start, end)
    if not loss.empty and "商品名称" in loss.columns:
        loss_names = loss["商品名称"].astype(str).str.strip()
        loss_mask = loss_names.str.lower().str.contains(q_lower, na=False)
        if by_barcode and barcodes:
            barcode_col = "商品条码" if "商品条码" in loss.columns else ("条码" if "条码" in loss.columns else None)
            if barcode_col:
                loss_mask |= loss[barcode_col].astype(str).str.strip().isin(barcodes)
        matched_loss = loss[loss_mask].copy()
        if not matched_loss.empty:
            qty_col = "报废数量" if "报废数量" in matched_loss.columns else "数量"
            amount_col = "报损金额" if "报损金额" in matched_loss.columns else "金额"
            loss_quantity = round(float(pd.to_numeric(matched_loss.get(qty_col, 0), errors="coerce").fillna(0).sum()), 2)
            loss_amount = round(float(pd.to_numeric(matched_loss.get(amount_col, 0), errors="coerce").fillna(0).sum()), 2)
            reasons: List[Dict[str, Any]] = []
            if "报损原因" in matched_loss.columns:
                for reason, group in matched_loss.groupby("报损原因"):
                    reasons.append(
                        {
                            "reason": str(reason),
                            "quantity": round(float(pd.to_numeric(group.get(qty_col, 0), errors="coerce").fillna(0).sum()), 2),
                            "amount": round(float(pd.to_numeric(group.get(amount_col, 0), errors="coerce").fillna(0).sum()), 2),
                        }
                    )
            loss_summary = {
                "total_quantity": loss_quantity,
                "total_amount": loss_amount,
                "reasons": reasons,
            }

    return {
        "analysis": "product_sales",
        "found": True,
        "query": query_str,
        "window": f"{start} ~ {end}",
        "total_quantity": total_quantity,
        "total_revenue": total_revenue,
        "order_count": order_count,
        "avg_price": avg_price,
        "total_profit": total_profit,
        "has_name_alias": has_name_alias,
        "alias_note": (
            f"检测到该商品存在改名或同条码关联（涉及名称：{'、'.join(unique_names)}），已自动合并统计。"
            if has_name_alias
            else ""
        ),
        "name_breakdown": name_breakdown,
        "monthly_breakdown": monthly_breakdown,
        "loss_summary": loss_summary,
    }
