"""Parameterized analysis tools for the AI assistant.

Wraps the legacy pure-pandas analysis functions (skills/forecast_alert/scripts/)
and feeds them data from the current dashboard data layer (pospal_live_data +
weather_api). Schema drift introduced since those scripts were written is fixed
here in the adapter — the legacy scripts stay untouched:

* weather labels from the API are ``晴/多云/阴/小雨/...`` while the legacy
  scripts expect ``晴天`` as the baseline label — normalized in
  :func:`_normalize_weather`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

MAX_WINDOW_DAYS = 90


# --------------------------------------------------------------------------- #
# Window resolution (same date_spec contract as fetch_pospal_data)
# --------------------------------------------------------------------------- #
def resolve_window(date_spec: Any, default_days: int = 30) -> Tuple[date, date]:
    """Return (start, end) date window from a date_spec dict.

    Supports preset / year+month / date_from~date_to; falls back to the last
    ``default_days`` days ending today. Window is clamped to 90 days and to
    today (no future data).
    """
    today = date.today()
    if isinstance(date_spec, dict) and "preset" in date_spec:
        preset = str(date_spec["preset"])
        if preset == "today":
            start = end = today
        elif preset == "yesterday":
            start = end = today - timedelta(days=1)
        elif preset == "week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
        else:  # month / default
            start = today.replace(day=1)
            end = today
    elif isinstance(date_spec, dict) and "year" in date_spec and "month" in date_spec:
        y, m = int(date_spec["year"]), int(date_spec["month"])
        start = date(y, m, 1)
        end = date(y, m, 28)
        while end.month == m:
            end += timedelta(days=1)
        end -= timedelta(days=1)
    elif isinstance(date_spec, dict) and (
        date_spec.get("date_from") or date_spec.get("date_to")
    ):
        df, dt = date_spec.get("date_from"), date_spec.get("date_to")
        start = date.fromisoformat(df) if df else today
        end = date.fromisoformat(dt) if dt else today
        if start > end:
            raise ValueError("date_from 不能晚于 date_to")
    else:
        start = today - timedelta(days=default_days)
        end = today

    # Never look into the future; cap the window span (trim the start, keep
    # explicit historical windows like "2026-03" intact).
    end = min(end, today)
    if (end - start).days > MAX_WINDOW_DAYS:
        start = end - timedelta(days=MAX_WINDOW_DAYS)
    if start > end:
        start = end
    return start, end

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
# Data access (reuses the cached PosPal + weather layers)
# --------------------------------------------------------------------------- #
def _fetch_sales_window(start: date, end: date) -> pd.DataFrame:
    """Daily revenue rows (日期, 实收金额) over [start, end], from cached PosPal."""
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
        return pd.DataFrame(columns=["日期", "实收金额"])
    out = pd.concat(frames, ignore_index=True)
    out["日期"] = pd.to_datetime(out["日期"])
    mask = (out["日期"].dt.date >= start) & (out["日期"].dt.date <= end)
    return out[mask]


def _fetch_sales_full_window(start: date, end: date) -> pd.DataFrame:
    """Full sales rows (流水号, 商品名称, 销售时间, 小时, 销售数量, 实收金额) over [start, end]."""
    from modules.pospal_live_data import fetch_live_pospal_data

    frames: List[pd.DataFrame] = []
    for year, month in _month_span(start, end):
        live = fetch_live_pospal_data(year, month)
        sales = live.sales
        if sales is None or sales.empty:
            continue
        cols = [c for c in ["流水号", "商品名称", "销售时间", "小时", "销售数量", "实收金额", "商品分类"] if c in sales.columns]
        df = sales[cols].copy()
        df["日期"] = pd.to_datetime(df.get("销售时间"), errors="coerce").dt.date
        frames.append(df[df["日期"].notna()])
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    mask = (out["日期"] >= start) & (out["日期"] <= end)
    return out[mask]


def _fetch_weather_window(start: date, end: date) -> pd.DataFrame:
    from modules.weather_api import fetch_humen_daily_weather

    result = fetch_humen_daily_weather(start, end)
    return result.data if result.data is not None else pd.DataFrame()


def _normalize_weather(df_w: pd.DataFrame) -> pd.DataFrame:
    """Map API weather labels to the legacy scripts' expectations (晴天 baseline)."""
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
    """Sales forecast: tomorrow (4 same-weekdays weighted avg) or next week."""
    if horizon not in ("tomorrow", "next_week"):
        raise ValueError("horizon 必须是 tomorrow 或 next_week")
    start, end = resolve_window(date_spec, default_days=45)
    sales = _fetch_sales_window(start, end)
    if sales.empty:
        return {"analysis": "forecast", "error": "窗口内无销售数据", "窗口": f"{start} ~ {end}"}
    sales = sales.copy()
    sales["日期"] = pd.to_datetime(sales["日期"])

    if horizon == "next_week":
        from skills.forecast_alert.scripts.prediction import predict_next_week

        result = predict_next_week(sales)
    else:
        from skills.forecast_alert.scripts.prediction import predict_tomorrow

        result = predict_tomorrow(sales)

    return {
        "analysis": "forecast",
        "horizon": horizon,
        "窗口": f"{start} ~ {end}",
        "数据天数": int(sales["日期"].dt.date.nunique()),
        "result": result,
    }


def run_weather_impact(date_spec: Any) -> Dict[str, Any]:
    """Weather vs. sales impact (晴 baseline coefficients) + severe weather alert."""
    start, end = resolve_window(date_spec, default_days=30)
    sales = _fetch_sales_window(start, end)
    sales = sales.copy()
    if not sales.empty:
        sales["日期"] = pd.to_datetime(sales["日期"])
    weather = _normalize_weather(_fetch_weather_window(start, end))
    if sales.empty or weather.empty:
        return {
            "analysis": "weather",
            "error": "窗口内销售或天气数据不足",
            "窗口": f"{start} ~ {end}",
        }

    from skills.forecast_alert.scripts.weather_impact import (
        weather_alert,
        weather_impact_summary,
    )

    impact = weather_impact_summary(sales, weather)
    alert = weather_alert(weather, sales)
    return {
        "analysis": "weather",
        "窗口": f"{start} ~ {end}",
        "天气覆盖天数": int(weather["日期"].nunique()) if "日期" in weather.columns else 0,
        "影响系数": None if impact is None else impact.to_dict("records"),
        "预警": alert,
    }


def run_basket_analysis(
    date_spec: Any = None,
    target_product: str | None = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    """Market basket & cross-selling analysis (连带率与关联商品)."""
    start, end = resolve_window(date_spec, default_days=30)
    sales = _fetch_sales_full_window(start, end)
    if sales.empty:
        return {
            "analysis": "basket",
            "error": "窗口内无销售明细数据",
            "窗口": f"{start} ~ {end}",
        }

    from skills.deep_analysis.scripts.basket_analysis import analyze_basket_cross_sell

    res = analyze_basket_cross_sell(sales, target_product=target_product, top_n=top_n)
    res["analysis"] = "basket"
    res["窗口"] = f"{start} ~ {end}"
    return res


def run_hourly_traffic(date_spec: Any = None) -> Dict[str, Any]:
    """Hourly traffic & revenue pattern analysis (24小时时段客流画像)."""
    start, end = resolve_window(date_spec, default_days=30)
    sales = _fetch_sales_full_window(start, end)
    if sales.empty:
        return {
            "analysis": "hourly",
            "error": "窗口内无销售明细数据",
            "窗口": f"{start} ~ {end}",
        }

    from skills.deep_analysis.scripts.hourly_traffic import analyze_hourly_traffic

    res = analyze_hourly_traffic(sales)
    res["analysis"] = "hourly"
    res["窗口"] = f"{start} ~ {end}"
    return res


def run_product_abc(
    date_spec: Any = None,
    top_a_pct: float = 0.70,
    top_b_pct: float = 0.90,
) -> Dict[str, Any]:
    """Product ABC structure & slow movers diagnosis (商品ABC分类与滞销淘汰)."""
    start, end = resolve_window(date_spec, default_days=30)
    sales = _fetch_sales_full_window(start, end)
    if sales.empty:
        return {
            "analysis": "abc",
            "error": "窗口内无销售数据",
            "窗口": f"{start} ~ {end}",
        }

    from skills.deep_analysis.scripts.product_abc import analyze_product_abc

    res = analyze_product_abc(sales, top_a_pct=top_a_pct, top_b_pct=top_b_pct)
    res["analysis"] = "abc"
    res["窗口"] = f"{start} ~ {end}"
    return res


def _fetch_recharge_window(start: date, end: date) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch sales_detail and cards_detail over [start, end]."""
    from modules.pospal_live_data import fetch_live_pospal_data

    sales_details: List[pd.DataFrame] = []
    cards_details: List[pd.DataFrame] = []

    for year, month in _month_span(start, end):
        live = fetch_live_pospal_data(year, month)
        if live.sales_detail is not None and not live.sales_detail.empty:
            df_sd = live.sales_detail.copy()
            if "日期" in df_sd.columns:
                df_sd["_d"] = pd.to_datetime(df_sd["日期"], errors="coerce").dt.date
                sales_details.append(df_sd[df_sd["_d"].notna()])
            else:
                sales_details.append(df_sd)

        if live.cards_detail is not None and not live.cards_detail.empty:
            df_cd = live.cards_detail.copy()
            if "充值时间" in df_cd.columns:
                df_cd["_d"] = pd.to_datetime(df_cd["充值时间"], errors="coerce").dt.date
                cards_details.append(df_cd[df_cd["_d"].notna()])
            else:
                cards_details.append(df_cd)

    s_out = pd.concat(sales_details, ignore_index=True) if sales_details else pd.DataFrame()
    c_out = pd.concat(cards_details, ignore_index=True) if cards_details else pd.DataFrame()

    if not s_out.empty and "_d" in s_out.columns:
        s_out = s_out[(s_out["_d"] >= start) & (s_out["_d"] <= end)].drop(columns=["_d"])
    if not c_out.empty and "_d" in c_out.columns:
        c_out = c_out[(c_out["_d"] >= start) & (c_out["_d"] <= end)].drop(columns=["_d"])

    return s_out, c_out


def run_recharge_health(date_spec: Any = None) -> Dict[str, Any]:
    """Recharge & cash flow health analysis (储值卡消耗与现金流健康度)."""
    start, end = resolve_window(date_spec, default_days=30)
    sales_detail, cards_detail = _fetch_recharge_window(start, end)
    if sales_detail.empty and cards_detail.empty:
        return {
            "analysis": "recharge",
            "error": "窗口内无充值与小票单据数据",
            "窗口": f"{start} ~ {end}",
        }

    from skills.profit_cost.scripts.recharge_health import analyze_recharge_health

    res = analyze_recharge_health(sales_detail, cards_detail)
    res["analysis"] = "recharge"
    res["窗口"] = f"{start} ~ {end}"
    return res


