"""
JSON-ready dashboard aggregation for the direct web frontend.
"""

from __future__ import annotations

import calendar
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from modules.pospal_live_data import LivePospalData, fetch_live_pospal_data
from modules.weather_api import (
    WEATHER_TIMEZONE,
    WeatherApiResult,
    fetch_store_daily_weather,
)


@dataclass(frozen=True)
class DashboardQuery:
    year: int
    month: int
    # Optional explicit date range (inclusive). When set, takes precedence
    # over year/month for date-bounded helpers.
    date_from: str | None = None  # YYYY-MM-DD
    date_to: str | None = None    # YYYY-MM-DD

    @classmethod
    def current(cls) -> "DashboardQuery":
        now = datetime.now()
        return cls(year=now.year, month=now.month)

    @classmethod
    def from_preset(cls, preset: str) -> "DashboardQuery":
        """Build a query for a named time-range preset (today/yesterday/week/month)."""
        today = date.today()
        now = datetime.now()
        if preset == "today":
            d = today.strftime("%Y-%m-%d")
            return cls(year=now.year, month=now.month, date_from=d, date_to=d)
        if preset == "yesterday":
            y = today - timedelta(days=1)
            d = y.strftime("%Y-%m-%d")
            return cls(year=now.year, month=now.month, date_from=d, date_to=d)
        if preset == "week":
            # Monday → Sunday of the current ISO week
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return cls(year=now.year, month=now.month,
                       date_from=start.strftime("%Y-%m-%d"),
                       date_to=end.strftime("%Y-%m-%d"))
        # default: current calendar month
        return cls.current()

    def label(self) -> str:
        if self.date_from and self.date_to:
            if self.date_from == self.date_to:
                return self.date_from
            return f"{self.date_from} → {self.date_to}"
        return f"{self.year}-{self.month:02d}"


def _parse_query_date(value: str | None) -> date | None:
    if not value:
        return None
    return pd.to_datetime(value, errors="raise").date()


def _month_span(start: date, end: date) -> Iterable[tuple[int, int]]:
    year = start.year
    month = start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def _concat_live_data(parts: list[LivePospalData]) -> LivePospalData:
    def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
        non_empty = [frame for frame in frames if not frame.empty]
        if not non_empty:
            return pd.DataFrame()
        return pd.concat(non_empty, ignore_index=True)

    return LivePospalData(
        sales=_concat([part.sales for part in parts]),
        loss=_concat([part.loss for part in parts]),
        cards=_concat([part.cards for part in parts]),
        cards_detail=_concat([part.cards_detail for part in parts]),
        sales_detail=_concat([part.sales_detail for part in parts]),
        payments=_concat([part.payments for part in parts]),
    )


def _date_mask(df: pd.DataFrame, date_col: str, query: "DashboardQuery") -> pd.Series:
    df_from = _parse_query_date(query.date_from)
    df_to = _parse_query_date(query.date_to)
    if date_col not in df.columns:
        return pd.Series(True, index=df.index)
    # Normalize to midnight datetime64[ns] so we can compare a uniform dtype
    # against pd.Timestamp. (Calling .dt.date and then comparing Python
    # `date` objects fails on recent pandas when the column is already
    # datetime64[ns].) Midnight-normalization also makes `date_to` inclusive
    # through end of day.
    dates = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
    mask = pd.Series(True, index=df.index)
    if df_from:
        mask &= dates >= pd.Timestamp(df_from)
    if df_to:
        mask &= dates <= pd.Timestamp(df_to)
    return mask.fillna(False)


def _filter_frame_by_query(df: pd.DataFrame, date_col: str, query: "DashboardQuery") -> pd.DataFrame:
    if df.empty or date_col not in df.columns or (not query.date_from and not query.date_to):
        return df
    return df[_date_mask(df, date_col, query)].copy()


def _filter_by_query(
    sales: pd.DataFrame,
    loss: pd.DataFrame,
    cards: pd.DataFrame,
    cards_detail: pd.DataFrame,
    sales_detail: pd.DataFrame,
    query: "DashboardQuery",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Filter all date-bounded dataframes by the query's inclusive date range."""
    if not query.date_from and not query.date_to:
        return sales, loss, cards, cards_detail, sales_detail
    return (
        _filter_frame_by_query(sales, "日期", query),
        _filter_frame_by_query(loss, "调整日期", query),
        _filter_frame_by_query(cards, "日期", query),
        _filter_frame_by_query(cards_detail, "日期", query),
        _filter_frame_by_query(sales_detail, "日期", query),
    )


def get_dashboard_payload(
    query: "DashboardQuery", *, force_refresh: bool = False
) -> Dict[str, Any]:
    start = _parse_query_date(query.date_from)
    end = _parse_query_date(query.date_to)
    if start and end and start > end:
        raise ValueError("date_from cannot be later than date_to")
    if start and end:
        live = _concat_live_data([
            fetch_live_pospal_data(year, month, force_refresh=force_refresh)
            for year, month in _month_span(start, end)
        ])
    else:
        live = fetch_live_pospal_data(
            query.year, query.month, force_refresh=force_refresh
        )
    weather_start, weather_end = _query_weather_span(query)
    if weather_start and weather_end:
        try:
            weather = fetch_store_daily_weather(
                weather_start,
                weather_end,
                force_refresh=force_refresh,
            )
        except Exception as exc:  # pragma: no cover - final network safeguard
            weather = WeatherApiResult(
                data=pd.DataFrame(),
                status="unavailable",
                message=f"虎门天气暂不可用：{exc}",
            )
    else:
        weather = WeatherApiResult(
            data=pd.DataFrame(),
            status="unavailable",
            message="所选日期尚无可用天气记录",
        )
    return build_dashboard_payload(live, query, weather=weather)


def _query_weather_span(query: "DashboardQuery") -> Tuple[date | None, date | None]:
    start = _parse_query_date(query.date_from)
    end = _parse_query_date(query.date_to)
    if not start or not end:
        start = date(query.year, query.month, 1)
        end = date(query.year, query.month, calendar.monthrange(query.year, query.month)[1])
    today = datetime.now(ZoneInfo(WEATHER_TIMEZONE)).date()
    end = min(end, today)
    if start > end:
        return None, None
    return start, end


def build_dashboard_payload(
    live: LivePospalData,
    query: "DashboardQuery",
    *,
    weather: WeatherApiResult | None = None,
) -> Dict[str, Any]:
    sales = _normalize_sales(live.sales)
    loss = live.loss.copy()
    cards = live.cards.copy()
    cards_detail = live.cards_detail.copy()
    sales_detail = live.sales_detail.copy() if not live.sales_detail.empty else live.sales_detail
    payments = live.payments.copy() if not live.payments.empty else live.payments

    # Apply date-range filter to every date-bounded dataset.
    sales, loss, cards, cards_detail, sales_detail = _filter_by_query(
        sales,
        loss,
        cards,
        cards_detail,
        sales_detail,
        query,
    )
    payments = _filter_frame_by_query(payments, "日期", query)
    sales_payments = _subtract_recharges_from_payments(payments, cards_detail)

    financial_params = _load_financial_parameters()
    daily = _build_daily_summary(sales, loss, cards, financial_params)
    if weather is None:
        weather = WeatherApiResult(
            data=pd.DataFrame(),
            status="unavailable",
            message="此数据路径未加载天气接口",
        )
    kpis = _build_kpis(sales, loss, cards, daily)
    _, last_day = calendar.monthrange(query.year, query.month)

    def _safe(name: str, fn, default):
        """Run a builder, returning a default if it fails so the dashboard never 500s on data quirks."""
        try:
            return fn()
        except Exception as exc:  # pragma: no cover - defensive
            import logging
            logging.getLogger("dashboard").warning("builder %s failed: %s", name, exc)
            return default

    return {
        "meta": {
            "year": query.year,
            "month": query.month,
            "dateFrom": query.date_from,
            "dateTo": query.date_to,
            "range": query.label(),
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "银豹后台接口",
            "weatherSource": weather.provider,
            "weatherStatus": weather.status,
        },
        "kpis": kpis,
        "kpiDeltas": _safe("kpiDeltas", lambda: _build_kpi_deltas(daily), {}),
        "cumulative": _safe("cumulative", lambda: _build_cumulative(daily), {}),
        "daily": _records(daily),
        "hourly": _records(_safe("hourly", lambda: _hourly_sales(sales), pd.DataFrame())),
        "incomeCategories": _records(_income_categories(sales)),
        "sources": _records(_source_breakdown(sales)),
        "topProducts": _records(_top_products(sales)),
        "lossReasons": _records(_loss_reasons(loss)),
        "cards": _records(_card_daily(cards)),
        "recharge": _records(_recharge_summary(cards_detail)),
        # --- Business insights ---
        "weekdayPattern": _records(_weekday_pattern(sales)),
        "weekendVsWeekday": _safe("weekendVsWeekday", lambda: _weekend_vs_weekday(sales), {}),
        "productABC": _records(_product_abc(sales)),
        "slowMovers": _records(_slow_movers(sales)),
        "lossDailyAnomaly": _records(_loss_daily_anomaly(daily)),
        "categoryMargin": _records(_category_margin(sales)),
        "cardNet": _records(_card_net_balance(cards)),
        "efficiency": _safe("efficiency", lambda: _build_efficiency(daily, financial_params), {}),
        "alerts": _safe("alerts", lambda: _build_alerts(sales, daily, cards, kpis, financial_params), []),
        # --- Analytics carried forward from the legacy dashboard ---
        "orderHeatmap": _records(_order_heatmap(sales)),
        "hourPeriod": _safe("hourPeriod", lambda: _hour_period(sales), {}),
        "highValueOrders": _safe("highValueOrders", lambda: _high_value_orders(sales), {}),
        "ticketDistribution": _records(_ticket_distribution(sales)),
        "lossByCategory": _records(_loss_by_category(loss)),
        "cardSummary": _safe("cardSummary", lambda: _build_card_summary(cards, cards_detail), {}),
        # --- Statistical / multi-month ---
        "volatility": _safe("volatility", lambda: _build_volatility(daily), {}),
        "concentration": _safe("concentration", lambda: _build_concentration(sales), {}),
        "categoryByHour": _records(_category_by_hour(sales)),
        "orderAmountDist": _records(_order_amount_distribution(sales)),
        # --- Deep PosPal field mining ---
        "discounts": _safe("discounts", lambda: _build_discounts(sales, sales_detail), {}),
        "paymentMix": _safe(
            "paymentMix",
            lambda: _build_payment_mix(sales_payments if not sales_payments.empty else sales_detail, sales),
            {"methods": [], "total": 0, "status": "unavailable"},
        ),
        "weatherDaily": _safe(
            "weatherDaily",
            lambda: _build_weather_daily(weather),
            {
                "status": "unavailable",
                "message": "虎门天气记录暂不可用",
                "latest": None,
                "days": [],
            },
        ),
        "weatherSales": _safe(
            "weatherSales",
            lambda: _build_weather_sales(daily, weather),
            {
                "status": "unavailable",
                "summary": {},
                "byCondition": [],
                "timeline": [],
                "scatter": [],
                "table": [],
            },
        ),
        "ticketType": _safe("ticketType", lambda: _build_ticket_type(sales_detail), {"types": [], "total": 0}),
        "profitByProduct": _records(_profit_by_product(sales)),
        "lossByReason": _safe("lossByReason", lambda: _build_loss_by_reason(loss), {"reasons": [], "totalAmount": 0, "totalQuantity": 0}),
        "memberSummary": _safe("memberSummary", lambda: _build_member_summary(cards_detail, cards), {}),
        "cardBalance": _safe("cardBalance", lambda: _build_card_balance(cards_detail, cards), {}),
        "pospalOverview": _safe("pospalOverview", lambda: _build_pospal_overview(sales, sales_detail, cards_detail, query), {}),
        "openCloseHours": _safe("openCloseHours", lambda: _build_open_close_hours(sales), {}),
        "calendar": _records(_build_calendar(daily, query.year, query.month)),
        "raw": {
            "sales": _records(_safe_head(sales, 300)),
            "loss": _records(_safe_head(loss, 200)),
            "cards": _records(_safe_head(cards, 200)),
            "cardsDetail": _records(_safe_head(cards_detail, 200)),
            "salesDetail": _records(_safe_head(sales_detail, 200)),
            "payments": _records(_safe_head(payments, 200)),
        },
    }


def _subtract_recharges_from_payments(
    payments: pd.DataFrame, cards_detail: pd.DataFrame
) -> pd.DataFrame:
    """Convert PosPal's all-business payment summary to merchandise sales only."""
    if payments.empty or cards_detail.empty or "支付分类" not in cards_detail.columns:
        return payments
    recharge = cards_detail.copy()
    recharge["日期"] = pd.to_datetime(recharge["日期"], errors="coerce").dt.normalize()
    recharge["支付方式"] = recharge["支付分类"].fillna("未分类").astype(str)
    recharge["充值金额"] = pd.to_numeric(recharge.get("充值金额"), errors="coerce").fillna(0)
    recharge = recharge.groupby(["日期", "支付方式"], as_index=False).agg(
        充值金额=("充值金额", "sum"),
        充值笔数=("充值金额", "size"),
    )

    result = payments.copy()
    result["日期"] = pd.to_datetime(result["日期"], errors="coerce").dt.normalize()
    result = result.merge(recharge, on=["日期", "支付方式"], how="left")
    result["金额"] = (
        pd.to_numeric(result["金额"], errors="coerce").fillna(0)
        - result["充值金额"].fillna(0)
    ).clip(lower=0)
    result["支付笔数"] = (
        pd.to_numeric(result["支付笔数"], errors="coerce").fillna(0)
        - result["充值笔数"].fillna(0)
    ).clip(lower=0)
    return result[result["金额"] > 0].drop(columns=["充值金额", "充值笔数"])


def _normalize_sales(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return sales
    df = sales.copy()
    df["收入分类"] = df["收入分类"].replace({"": "未分类", "无": "未分类"}).fillna("未分类")
    df["商品分类"] = df["商品分类"].replace({"": "未分类", "无": "未分类"}).fillna("未分类")
    df["来源"] = df["来源"].fillna("门店")
    return df


def _build_daily_summary(
    sales: pd.DataFrame,
    loss: pd.DataFrame,
    cards: pd.DataFrame,
    financial_params: Dict[str, float] | None = None,
) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame()

    daily = (
        sales.groupby("日期")
        .agg(
            实收金额=("实收金额", "sum"),
            商品总价=("商品总价", "sum"),
            销售数量=("销售数量", "sum"),
            订单笔数=("流水号", "nunique"),
        )
        .reset_index()
    )

    if not loss.empty and "调整日期" in loss.columns:
        loss_daily = (
            loss.groupby("调整日期")
            .agg(损耗价值=("报损金额", "sum"), 报废数量=("报废数量", "sum"))
            .reset_index()
            .rename(columns={"调整日期": "日期"})
        )
        daily = daily.merge(loss_daily, on="日期", how="left")
    else:
        daily["损耗价值"] = 0
        daily["报废数量"] = 0

    if not cards.empty and "日期" in cards.columns:
        card_temp = cards.copy()
        card_temp["日期"] = card_temp["日期"].dt.date
        card_daily = (
            card_temp.groupby("日期")
            .agg(储值卡充值=("充值总金额", "sum"), 储值卡消费=("储值卡消费总金额", "sum"))
            .reset_index()
        )
        daily = daily.merge(card_daily, on="日期", how="left")
    else:
        daily["储值卡充值"] = 0
        daily["储值卡消费"] = 0

    daily = daily.fillna(0).sort_values("日期")
    if financial_params is None:
        financial_params = _load_financial_parameters()
    daily["商品成本估算"] = daily["商品总价"] * financial_params["原料成本比"]
    daily["固定支出"] = financial_params["固定支出"]
    daily["净利润估算"] = (
        daily["实收金额"] - daily["商品成本估算"] - daily["固定支出"]
    )
    daily["客单价"] = daily["实收金额"] / daily["订单笔数"].replace(0, pd.NA)
    daily["报损率"] = daily["损耗价值"] / daily["商品总价"].replace(0, pd.NA)
    daily["日期"] = daily["日期"].astype(str)
    return daily.fillna(0)


def _load_financial_parameters() -> Dict[str, float]:
    """Load compact deployment settings or fall back to the local databases."""
    if os.environ.get("VERCEL"):
        return {
            "固定支出": float(os.environ.get("DASHBOARD_FIXED_COST", "5000")),
            "原料成本比": float(os.environ.get("DASHBOARD_RAW_MATERIAL_RATIO", "0.4")),
            "运营管理": float(os.environ.get("DASHBOARD_OPERATING_RATIO", "0.0438")),
        }

    # Keep the existing local/Streamlit behavior without making Streamlit and
    # the historical SQLite files part of the Vercel function bundle.
    from modules.financial import get_financial_parameters
    from modules.database import load_financial_data

    return get_financial_parameters(load_financial_data())


def _build_kpis(
    sales: pd.DataFrame,
    loss: pd.DataFrame,
    cards: pd.DataFrame,
    daily: pd.DataFrame,
) -> Dict[str, float]:
    total_revenue = _sum(sales, "实收金额")
    total_orders = float(sales["流水号"].nunique()) if not sales.empty and "流水号" in sales.columns else 0
    return {
        "revenue": total_revenue,
        "orders": total_orders,
        "avgTicket": total_revenue / total_orders if total_orders else 0,
        "loss": _sum(loss, "报损金额"),
        "cardRecharge": _sum(cards, "充值总金额"),
        "netProfit": _sum(daily, "净利润估算"),
    }


def _hourly_sales(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame(columns=["小时", "实收金额", "订单数"])
    return (
        sales.groupby("小时", as_index=False)
        .agg(实收金额=("实收金额", "sum"), 订单数=("流水号", "nunique"))
        .sort_values("小时")
    )


def _income_categories(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame(columns=["收入分类", "实收金额", "订单数", "销售数量"])
    return (
        sales.groupby("收入分类")
        .agg(实收金额=("实收金额", "sum"), 订单数=("流水号", "nunique"), 销售数量=("销售数量", "sum"))
        .reset_index()
        .sort_values("实收金额", ascending=False)
    )


def _source_breakdown(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame(columns=["来源", "实收金额", "订单数"])
    return (
        sales.groupby("来源")
        .agg(实收金额=("实收金额", "sum"), 订单数=("流水号", "nunique"))
        .reset_index()
        .sort_values("实收金额", ascending=False)
    )


def _top_products(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame(columns=["商品名称", "商品分类", "收入分类", "实收金额", "销售数量", "订单数"])
    return (
        sales.groupby(["商品名称", "商品分类", "收入分类"])
        .agg(实收金额=("实收金额", "sum"), 销售数量=("销售数量", "sum"), 订单数=("流水号", "nunique"))
        .reset_index()
        .sort_values("实收金额", ascending=False)
        .head(30)
    )


def _loss_reasons(loss: pd.DataFrame) -> pd.DataFrame:
    if loss.empty or "报损金额" not in loss.columns:
        return pd.DataFrame(columns=["报损原因", "报损金额", "报废数量"])
    temp = loss.copy()
    temp["报损原因"] = temp["报损原因"].replace("", "未填写").fillna("未填写")
    agg = {"报损金额": ("报损金额", "sum")}
    if "报废数量" in temp.columns:
        agg["报废数量"] = ("报废数量", "sum")
    out = temp.groupby("报损原因", as_index=False).agg(**agg)
    if "报废数量" not in out.columns:
        out["报废数量"] = 0
    return out.sort_values("报损金额", ascending=False)


def _card_daily(cards: pd.DataFrame) -> pd.DataFrame:
    if cards.empty:
        return pd.DataFrame(columns=["日期", "充值总金额", "储值卡消费总金额", "本金消费金额", "赠送消费金额"])
    df = cards.copy()
    df["日期"] = df["日期"].dt.date.astype(str)
    return df[["日期", "充值总金额", "储值卡消费总金额", "本金消费金额", "赠送消费金额"]]


def _recharge_summary(cards_detail: pd.DataFrame) -> pd.DataFrame:
    if cards_detail.empty or "充值金额" not in cards_detail.columns:
        return pd.DataFrame(columns=["支付分类", "充值金额", "赠送金额", "笔数"])
    temp = cards_detail.copy()
    if "支付分类" not in temp.columns:
        temp["支付分类"] = "未分类"
    return (
        temp.groupby("支付分类", as_index=False)
        .agg(充值金额=("充值金额", "sum"), 赠送金额=("赠送金额", "sum"), 笔数=("充值金额", "count"))
        .sort_values("充值金额", ascending=False)
    )


# =============================================================================
# Business insights helpers
# =============================================================================


def _build_kpi_deltas(daily: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Compute month-on-month style deltas using the second half vs first half of the month."""
    if daily.empty:
        return {}
    half = len(daily) // 2
    if half == 0:
        return {
            "revenue": {"delta": 0, "trend": "flat"},
            "orders": {"delta": 0, "trend": "flat"},
            "avgTicket": {"delta": 0, "trend": "flat"},
            "netProfit": {"delta": 0, "trend": "flat"},
        }
    first = daily.iloc[:half]
    second = daily.iloc[half:]

    def _delta(field: str) -> float:
        a = first[field].sum() if field in first.columns else 0
        b = second[field].sum() if field in second.columns else 0
        if a == 0:
            return 0
        return (b - a) / a

    def _trend(d: float) -> str:
        if d > 0.02:
            return "up"
        if d < -0.02:
            return "down"
        return "flat"

    return {
        "revenue": {"delta": _delta("实收金额"), "trend": _trend(_delta("实收金额"))},
        "orders": {"delta": _delta("订单笔数"), "trend": _trend(_delta("订单笔数"))},
        "avgTicket": {"delta": _delta("客单价"), "trend": _trend(_delta("客单价"))},
        "netProfit": {"delta": _delta("净利润估算"), "trend": _trend(_delta("净利润估算"))},
    }


def _weekday_pattern(sales: pd.DataFrame) -> pd.DataFrame:
    """Revenue by day-of-week for the current month, with weekly heatmap rows."""
    if sales.empty or "销售时间" not in sales.columns:
        return pd.DataFrame(columns=["日期", "周几", "实收金额", "订单数"])
    df = sales.copy()
    df["日期"] = df["销售时间"].dt.date.astype(str)
    df["周几"] = df["销售时间"].dt.dayofweek
    out = (
        df.groupby(["日期", "周几"], as_index=False)
        .agg(实收金额=("实收金额", "sum"), 订单数=("流水号", "nunique"))
        .sort_values(["日期"])
    )
    return out


def _weekend_vs_weekday(sales: pd.DataFrame) -> Dict[str, Any]:
    if sales.empty or "销售时间" not in sales.columns:
        return {"weekdayRevenue": 0, "weekendRevenue": 0, "weekdayOrders": 0, "weekendOrders": 0}
    df = sales.copy()
    df["_isWeekend"] = df["销售时间"].dt.dayofweek >= 5
    weekday = df[~df["_isWeekend"]]
    weekend = df[df["_isWeekend"]]
    return {
        "weekdayRevenue": float(weekday["实收金额"].sum()),
        "weekendRevenue": float(weekend["实收金额"].sum()),
        "weekdayOrders": float(weekday["流水号"].nunique()),
        "weekendOrders": float(weekend["流水号"].nunique()),
        "weekdayDays": int(weekday["销售时间"].dt.date.nunique()),
        "weekendDays": int(weekend["销售时间"].dt.date.nunique()),
    }


def _product_abc(sales: pd.DataFrame) -> pd.DataFrame:
    """Pareto / ABC classification — top 80% revenue items are A, next 15% B, rest C."""
    if sales.empty:
        return pd.DataFrame(columns=["商品名称", "实收金额", "累计占比", "ABC分类"])
    top = (
        sales.groupby("商品名称", as_index=False)
        .agg(实收金额=("实收金额", "sum"), 销售数量=("销售数量", "sum"))
        .sort_values("实收金额", ascending=False)
    )
    total = top["实收金额"].sum()
    if total == 0:
        return top.assign(累计占比=0.0, ABC分类="C")
    top["累计占比"] = (top["实收金额"].cumsum() / total).round(4)

    def _abc(cum: float) -> str:
        if cum <= 0.8:
            return "A"
        if cum <= 0.95:
            return "B"
        return "C"

    top["ABC分类"] = top["累计占比"].apply(_abc)
    return top


def _slow_movers(sales: pd.DataFrame) -> pd.DataFrame:
    """Bottom 10 by revenue but with at least 1 sale — candidates for promo or removal."""
    if sales.empty:
        return pd.DataFrame(columns=["商品名称", "商品分类", "实收金额", "销售数量", "订单数"])
    bottom = (
        sales.groupby(["商品名称", "商品分类"], as_index=False)
        .agg(实收金额=("实收金额", "sum"), 销售数量=("销售数量", "sum"), 订单数=("流水号", "nunique"))
        .sort_values("实收金额", ascending=True)
        .head(10)
    )
    return bottom


def _loss_daily_anomaly(daily: pd.DataFrame) -> pd.DataFrame:
    """Flag days whose loss-rate is > 1.5σ above the monthly mean (or above 5% absolute)."""
    if daily.empty or "损耗价值" not in daily.columns:
        return pd.DataFrame(columns=["日期", "损耗价值", "报损率", "异常", "严重程度"])
    df = daily[["日期", "损耗价值", "报损率"]].copy()
    df["报损率"] = pd.to_numeric(df["报损率"], errors="coerce").fillna(0)
    mean = df["报损率"].mean()
    std = df["报损率"].std()
    threshold = max(mean + 1.5 * std, 0.05) if std else 0.05

    def _severity(rate: float) -> str:
        if rate >= 0.10:
            return "critical"
        if rate >= threshold:
            return "warn"
        return "ok"

    df["异常"] = df["报损率"].apply(lambda r: bool(r >= threshold))
    df["严重程度"] = df["报损率"].apply(_severity)
    return df.sort_values("报损率", ascending=False)


def _category_margin(sales: pd.DataFrame) -> pd.DataFrame:
    """Estimate margin per 收入分类 using 商品总价 vs 实收金额 (POS yields cost via POS data, fallback to financial_params)."""
    if sales.empty:
        return pd.DataFrame(columns=["收入分类", "实收金额", "商品总价", "毛利率"])
    out = (
        sales.groupby("收入分类", as_index=False)
        .agg(实收金额=("实收金额", "sum"), 商品总价=("商品总价", "sum"))
    )
    out["毛利"] = (out["实收金额"] - out["商品总价"]).clip(lower=0)
    out["毛利率"] = (out["毛利"] / out["实收金额"].replace(0, pd.NA)).fillna(0)
    return out.sort_values("实收金额", ascending=False)


def _card_net_balance(cards: pd.DataFrame) -> pd.DataFrame:
    """Cumulative net (recharge - spend) card balance over time."""
    if cards.empty or "日期" not in cards.columns:
        return pd.DataFrame(columns=["日期", "净值", "累计余额"])
    df = cards.copy()
    df["日期"] = df["日期"].dt.date.astype(str)
    df["净值"] = (df["充值总金额"].fillna(0) - df["储值卡消费总金额"].fillna(0))
    df = df.sort_values("日期")
    df["累计余额"] = df["净值"].cumsum()
    return df[["日期", "净值", "累计余额"]]


def _build_efficiency(daily: pd.DataFrame, params: Dict[str, float]) -> Dict[str, float]:
    """Operational efficiency gauges: cost ratio, breakeven coverage, etc."""
    if daily.empty:
        return {"costRatio": 0, "breakevenDays": 0, "operatingDays": 0, "profitMargin": 0}
    revenue = daily["实收金额"].sum()
    cost = daily["商品成本估算"].sum() + daily["固定支出"].sum()
    profit = daily["净利润估算"].sum()
    cost_ratio = cost / revenue if revenue else 0
    profit_margin = profit / revenue if revenue else 0

    profitable = (daily["净利润估算"] > 0).sum()
    return {
        "costRatio": cost_ratio,
        "breakevenDays": int(profitable),
        "operatingDays": int(len(daily)),
        "profitMargin": profit_margin,
        "totalRevenue": float(revenue),
        "totalCost": float(cost),
    }


def _build_alerts(
    sales: pd.DataFrame,
    daily: pd.DataFrame,
    cards: pd.DataFrame,
    kpis: Dict[str, float],
    params: Dict[str, float],
) -> List[Dict[str, str]]:
    """Heuristic alerts: severe loss day, loss-day streak, low-margin category, low traffic, high balance growth."""
    alerts: List[Dict[str, str]] = []
    if not daily.empty and "报损率" in daily.columns:
        loss_rate = pd.to_numeric(daily["报损率"], errors="coerce").fillna(0)
        mean = loss_rate.mean()
        std = loss_rate.std() or 0.01
        worst_idx = loss_rate.idxmax()
        worst = daily.iloc[worst_idx] if worst_idx is not None else None
        if worst is not None and float(loss_rate.iloc[worst_idx]) >= max(mean + 1.5 * std, 0.08):
            alerts.append({
                "level": "critical",
                "title": "报损异常日",
                "detail": f"{worst['日期']} 报损率达 {loss_rate.iloc[worst_idx]*100:.1f}%（均值 {mean*100:.1f}%）",
            })
        if (loss_rate > 0.06).sum() >= 3:
            alerts.append({
                "level": "warn",
                "title": "持续高损耗",
                "detail": f"本月有 {(loss_rate > 0.06).sum()} 天报损率超过 6%，请检查库存与生产流程。",
            })

    if kpis.get("netProfit", 0) < 0:
        alerts.append({
            "level": "critical",
            "title": "本月净利润为负",
            "detail": f"估算净亏损 {money(kpis['netProfit'])}，建议复盘成本结构与定价。",
        })
    elif kpis.get("netProfit", 0) < kpis.get("revenue", 1) * 0.05:
        alerts.append({
            "level": "warn",
            "title": "净利润率偏低",
            "detail": "净利润率不足 5%，留意高损耗与折扣让利。",
        })

    if not daily.empty and kpis.get("orders", 0) > 0 and len(daily) > 0:
        avg_orders = kpis["orders"] / len(daily)
        if avg_orders < 30:
            alerts.append({
                "level": "warn",
                "title": "日均订单偏低",
                "detail": f"日均仅 {avg_orders:.0f} 单，可考虑推出套餐或外送活动。",
            })

    card_recharge = kpis.get("cardRecharge", 0)
    card_spend = 0
    if not cards.empty and "储值卡消费总金额" in cards.columns:
        card_spend = float(cards["储值卡消费总金额"].sum())
    if card_recharge > 0 and card_spend / card_recharge < 0.3:
        alerts.append({
            "level": "info",
            "title": "储值卡沉淀较多",
            "detail": "充值/消费比偏高，可策划会员日活动激活消费。",
        })

    return alerts


def _build_cumulative(daily: pd.DataFrame) -> Dict[str, Any]:
    """Build cumulative KPIs using the shared legacy-compatible formulas."""
    if daily.empty:
        return {
            "商品总价累计": 0, "实收金额累计": 0, "订单笔数累计": 0,
            "损耗价值累计": 0, "净利润累计": 0, "总净利润率": 0,
            "series": [],
        }
    cum_gross = float(daily["商品总价"].sum())
    cum_rev = float(daily["实收金额"].sum())
    cum_orders = float(daily["订单笔数"].sum())
    cum_loss = float(daily["损耗价值"].sum())
    cum_profit = float(daily["净利润估算"].sum())
    cum_margin = (cum_profit / cum_rev * 100) if cum_rev else 0

    # Build running cumulative series for net profit line
    series = []
    running = 0.0
    for _, row in daily.iterrows():
        running += float(row["净利润估算"] or 0)
        series.append({"日期": str(row["日期"]), "净利润累计": round(running, 2)})

    return {
        "商品总价累计": cum_gross,
        "实收金额累计": cum_rev,
        "订单笔数累计": cum_orders,
        "损耗价值累计": cum_loss,
        "净利润累计": cum_profit,
        "总净利润率": cum_margin,
        "series": series,
    }


def _order_heatmap(sales: pd.DataFrame) -> pd.DataFrame:
    """Date × hour orders heatmap (date, hour, orders, revenue)."""
    if sales.empty or "销售时间" not in sales.columns:
        return pd.DataFrame(columns=["日期", "小时", "订单数", "实收金额"])
    df = sales.copy()
    df["日期"] = df["销售时间"].dt.date.astype(str)
    df["小时"] = df["销售时间"].dt.hour
    out = (
        df.groupby(["日期", "小时"], as_index=False)
        .agg(订单数=("流水号", "nunique"), 实收金额=("实收金额", "sum"))
    )
    return out


def _hour_period(sales: pd.DataFrame) -> Dict[str, Any]:
    """Split sales into 早 9:30-12, 午 12-15, 下午 15-18 and 晚 18-24."""
    if sales.empty or "销售时间" not in sales.columns:
        return {
            "morning": {"订单数": 0, "实收金额": 0, "占比": 0},
            "noon": {"订单数": 0, "实收金额": 0, "占比": 0},
            "afternoon": {"订单数": 0, "实收金额": 0, "占比": 0},
            "evening": {"订单数": 0, "实收金额": 0, "占比": 0},
            "peak": {"hour": 0, "订单数": 0},
        }
    df = sales.copy()
    df["小时"] = df["销售时间"].dt.hour
    hourly = df.groupby("小时", as_index=False).agg(订单数=("流水号", "nunique"), 实收金额=("实收金额", "sum"))
    peak_idx = int(hourly["订单数"].idxmax()) if not hourly.empty else 0
    peak_row = hourly.iloc[peak_idx] if not hourly.empty else None

    def _bucket(h_low: int, h_high_exclusive: int) -> Dict[str, float]:
        mask = (df["小时"] >= h_low) & (df["小时"] < h_high_exclusive)
        sub = df[mask]
        return {"订单数": int(sub["流水号"].nunique()), "实收金额": float(sub["实收金额"].sum())}

    morning = _bucket(9, 12)
    noon = _bucket(12, 15)
    afternoon = _bucket(15, 18)
    evening = _bucket(18, 24)
    total_orders = morning["订单数"] + noon["订单数"] + afternoon["订单数"] + evening["订单数"]
    for b in (morning, noon, afternoon, evening):
        b["占比"] = (b["订单数"] / total_orders) if total_orders else 0
    return {
        "morning": morning, "noon": noon, "afternoon": afternoon, "evening": evening,
        "peak": {"hour": int(peak_row["小时"]), "订单数": int(peak_row["订单数"])} if peak_row is not None else {"hour": 0, "订单数": 0},
    }


def _high_value_orders(sales: pd.DataFrame) -> Dict[str, Any]:
    """Orders > ¥50, with size-bucket distribution and key KPIs."""
    if sales.empty or "流水号" not in sales.columns:
        return {
            "高价值订单数": 0, "总订单数": 0, "高价值订单占比": 0,
            "平均订单金额": 0, "高价值平均金额": 0,
            "buckets": [],
        }
    order_amounts = sales.groupby("流水号")["实收金额"].sum()
    high = order_amounts[order_amounts > 50]
    total = len(order_amounts)
    if total == 0:
        return {
            "高价值订单数": 0, "总订单数": 0, "高价值订单占比": 0,
            "平均订单金额": 0, "高价值平均金额": 0,
            "buckets": [],
        }
    bins = [50, 100, 150, 200, 300, float("inf")]
    labels = ["50–100", "100–150", "150–200", "200–300", "300+"]
    cats = pd.cut(high, bins=bins, labels=labels, right=False)
    counts = cats.value_counts().reindex(labels, fill_value=0)
    buckets = [{"区间": k, "订单数": int(v)} for k, v in counts.items()]
    return {
        "高价值订单数": int(len(high)),
        "总订单数": int(total),
        "高价值订单占比": (len(high) / total) if total else 0,
        "平均订单金额": float(order_amounts.mean()),
        "高价值平均金额": float(high.mean()) if len(high) else 0,
        "buckets": buckets,
    }


def _ticket_distribution(sales: pd.DataFrame) -> pd.DataFrame:
    """Average order value by hour (avg, orders, revenue) — hour-level ticket size view."""
    if sales.empty or "销售时间" not in sales.columns:
        return pd.DataFrame(columns=["小时", "客单价", "订单数", "实收金额"])
    df = sales.copy()
    df["小时"] = df["销售时间"].dt.hour
    out = df.groupby("小时", as_index=False).agg(
        订单数=("流水号", "nunique"),
        实收金额=("实收金额", "sum"),
    )
    out["客单价"] = (out["实收金额"] / out["订单数"].replace(0, pd.NA)).fillna(0)
    return out


def _loss_by_category(loss: pd.DataFrame) -> pd.DataFrame:
    """Group loss by 商品分类 (when available) for a stacked breakdown."""
    if loss.empty:
        return pd.DataFrame(columns=["商品分类", "报损金额", "报废数量"])
    cat_col = "商品分类" if "商品分类" in loss.columns else None
    if not cat_col:
        return pd.DataFrame()
    out = loss.groupby(cat_col, as_index=False).agg(
        报损金额=("报损金额", "sum") if "报损金额" in loss.columns else ("报废数量", "sum"),
        报废数量=("报废数量", "sum") if "报废数量" in loss.columns else ("报损金额", "count"),
    ).sort_values("报损金额", ascending=False)
    return out


def _build_card_summary(cards: pd.DataFrame, cards_detail: pd.DataFrame) -> Dict[str, Any]:
    """Build the shared stored-value card summary."""
    if cards.empty:
        return {
            "充值总金额": 0, "储值卡消费": 0, "本金消费": 0, "赠送消费": 0,
        }
    return {
        "充值总金额": float(cards["充值总金额"].sum()) if "充值总金额" in cards.columns else 0,
        "储值卡消费": float(cards["储值卡消费总金额"].sum()) if "储值卡消费总金额" in cards.columns else 0,
        "本金消费": float(cards["本金消费金额"].sum()) if "本金消费金额" in cards.columns else 0,
        "赠送消费": float(cards["赠送消费金额"].sum()) if "赠送消费金额" in cards.columns else 0,
    }


# =============================================================================
# Deep PosPal field mining
# =============================================================================


def _build_discounts(sales: pd.DataFrame, sales_detail: pd.DataFrame) -> Dict[str, Any]:
    """Discount / 优惠 metrics from sales_detail (商品原价 vs 实收金额) and sales 折让字段."""
    total_original = 0.0
    total_received = 0.0
    if not sales_detail.empty and "商品原价" in sales_detail.columns and "实收金额" in sales_detail.columns:
        total_original = float(sales_detail["商品原价"].sum())
        total_received = float(sales_detail["实收金额"].sum())
    elif not sales.empty and "商品原价" in sales.columns:
        total_original = float(sales["商品原价"].sum())
        total_received = float(sales["实收金额"].sum())
    discount_amt = max(0.0, total_original - total_received)
    discount_rate = (discount_amt / total_original) if total_original else 0
    # Per-day discount trend (last 7 days)
    daily_discount = []
    if not sales.empty and "日期" in sales.columns and "商品原价" in sales.columns:
        grp = sales.groupby("日期", as_index=False).agg(
            商品原价=("商品原价", "sum"),
            实收金额=("实收金额", "sum"),
        )
        for _, row in grp.iterrows():
            orig = float(row["商品原价"] or 0)
            recv = float(row["实收金额"] or 0)
            daily_discount.append({
                "日期": str(row["日期"]),
                "优惠金额": max(0.0, orig - recv),
                "优惠率": ((orig - recv) / orig) if orig else 0,
                "销售金额": orig,
                "实收金额": recv,
            })
    # Orders with discount (单子粒度)
    discounted_orders = 0
    total_orders = 0
    if not sales.empty and "流水号" in sales.columns and "商品原价" in sales.columns:
        order_lvl = sales.groupby("流水号").agg(
            原价=("商品原价", "sum"),
            实收=("实收金额", "sum"),
        )
        total_orders = int(len(order_lvl))
        discounted_orders = int((order_lvl["原价"] > order_lvl["实收"] + 0.01).sum())
    return {
        "销售金额": total_original,
        "实收金额": total_received,
        "优惠金额": discount_amt,
        "优惠率": discount_rate,
        "优惠单数": discounted_orders,
        "订单总数": total_orders,
        "优惠单占比": (discounted_orders / total_orders) if total_orders else 0,
        "dailyTrend": daily_discount,
    }


def _build_payment_mix(
    sales_detail: pd.DataFrame,
    sales: pd.DataFrame | None = None,
) -> Dict[str, Any]:
    """Build a cashier-style payment breakdown and reconciliation summary.

    Silver Leopard exports and OpenAPI adapters use several names for the same
    fields, so this accepts both the Chinese export columns and common API
    aliases.  When the payment fields are not present, the response explains
    why instead of making the HTML look like a zero-sales period.
    """
    sales = sales if sales is not None else pd.DataFrame()
    expected_revenue = (
        float(pd.to_numeric(sales["实收金额"], errors="coerce").fillna(0).sum())
        if not sales.empty and "实收金额" in sales.columns
        else 0.0
    )
    empty_result = {
        "methods": [],
        "total": 0.0,
        "methodCount": 0,
        "paymentCount": 0,
        "orderCount": 0,
        "mixedPaymentOrders": 0,
        "averagePerOrder": 0.0,
        "dominantMethod": None,
        "dominantShare": 0.0,
        "expectedRevenue": expected_revenue,
        "reconciliationGap": -expected_revenue if expected_revenue else 0.0,
        "coverage": 0.0 if expected_revenue else None,
        "reconciled": False,
        "status": "unavailable",
        "message": "当前银豹销售流水未返回支付方式字段",
    }
    if sales_detail.empty:
        return empty_result

    method_col = next(
        (
            col
            for col in ("支付方式", "支付分类", "支付名称", "payMethod", "paymentName")
            if col in sales_detail.columns
        ),
        None,
    )
    amount_col = next(
        (
            col
            for col in ("金额", "支付金额", "实收金额", "amount", "payAmount")
            if col in sales_detail.columns
        ),
        None,
    )
    if method_col is None or amount_col is None:
        return empty_result

    temp = sales_detail.copy()
    temp["_支付方式"] = (
        temp[method_col]
        .fillna("未分类")
        .astype(str)
        .str.strip()
        .replace({"": "未分类", "nan": "未分类", "None": "未分类"})
    )
    temp["_支付金额"] = pd.to_numeric(temp[amount_col], errors="coerce").fillna(0)
    order_col = "流水号" if "流水号" in temp.columns else None

    count_col = "支付笔数" if "支付笔数" in temp.columns else "_支付金额"
    count_op = "sum" if "支付笔数" in temp.columns else "size"
    agg: Dict[str, Tuple[str, str]] = {
        "金额": ("_支付金额", "sum"),
        "支付笔数": (count_col, count_op),
    }
    if order_col:
        agg["订单数"] = (order_col, "nunique")
    grp = temp.groupby("_支付方式", as_index=False, dropna=False).agg(**agg)
    if "订单数" not in grp.columns:
        grp["订单数"] = grp["支付笔数"]
    grp = grp.sort_values("金额", ascending=False)

    total = float(grp["金额"].sum())
    payment_count = int(grp["支付笔数"].sum())
    if order_col:
        order_count = int(temp[order_col].nunique())
    elif not sales.empty and "流水号" in sales.columns:
        order_count = int(sales["流水号"].nunique())
    else:
        order_count = payment_count
    mixed_payment_orders = 0
    if order_col:
        mixed_payment_orders = int(
            (temp.groupby(order_col)["_支付方式"].nunique() > 1).sum()
        )

    items = [
        {
            "支付方式": str(row["_支付方式"]),
            "金额": float(row["金额"]),
            "占比": (float(row["金额"]) / total) if total else 0,
            "支付笔数": int(row["支付笔数"]),
            "订单数": int(row["订单数"]),
            "平均每单": (
                float(row["金额"]) / int(row["订单数"])
                if int(row["订单数"])
                else 0
            ),
        }
        for _, row in grp.iterrows()
    ]
    gap = total - expected_revenue
    tolerance = max(0.01, abs(expected_revenue) * 0.001)
    return {
        "methods": items,
        "total": total,
        "methodCount": len(items),
        "paymentCount": payment_count,
        "orderCount": order_count,
        "mixedPaymentOrders": mixed_payment_orders,
        "averagePerOrder": (total / order_count) if order_count else 0,
        "dominantMethod": items[0]["支付方式"] if items else None,
        "dominantShare": items[0]["占比"] if items else 0,
        "expectedRevenue": expected_revenue,
        "reconciliationGap": gap,
        "coverage": (total / expected_revenue) if expected_revenue else None,
        "reconciled": bool(expected_revenue and abs(gap) <= tolerance),
        "status": "available",
        "message": "支付总额已与营业实收核对" if expected_revenue and abs(gap) <= tolerance else "请核对支付总额与营业实收差额",
    }


def _build_weather_daily(weather: WeatherApiResult) -> Dict[str, Any]:
    """Return current and historical Humen weather without revenue analysis."""
    base = {
        "status": weather.status,
        "message": weather.message,
        "provider": weather.provider,
        "location": weather.location,
        "latitude": weather.latitude,
        "longitude": weather.longitude,
        "fetchedAt": weather.fetched_at,
    }
    if weather.data.empty:
        return {**base, "status": "unavailable", "latest": None, "days": []}

    frame = weather.data.sort_values("日期", ascending=False)
    today = datetime.now(ZoneInfo(WEATHER_TIMEZONE)).date()

    def _float(row: pd.Series, name: str) -> float | None:
        value = row.get(name)
        return None if value is None or pd.isna(value) else float(value)

    def _day(row: pd.Series) -> Dict[str, Any]:
        weather_date = row.get("日期")
        date_text = (
            weather_date.isoformat()
            if hasattr(weather_date, "isoformat")
            else str(weather_date)
        )
        return {
            "date": date_text,
            "isToday": weather_date == today,
            "condition": str(row.get("天气") or "天气未知"),
            "category": str(row.get("天气类型") or "其他"),
            "icon": str(row.get("天气图标") or "◌"),
            "temperatureMax": _float(row, "最高温"),
            "temperatureMin": _float(row, "最低温"),
            "temperatureMean": _float(row, "平均温度"),
            "precipitation": _float(row, "降水量"),
            "rain": _float(row, "降雨量"),
            "precipitationHours": _float(row, "降水时长"),
            "sunshineHours": _float(row, "日照时长"),
            "windSpeedMax": _float(row, "最大风速"),
            "dataType": str(row.get("数据类型") or "天气数据"),
        }

    days = [_day(row) for _, row in frame.iterrows()]
    return {**base, "latest": days[0], "days": days}


def _build_weather_sales(
    daily: pd.DataFrame, weather: WeatherApiResult
) -> Dict[str, Any]:
    """Correlate daily sales with Humen weather to analyze weather impact on revenue."""
    unavailable = {
        "status": "unavailable",
        "summary": {},
        "byCondition": [],
        "timeline": [],
        "scatter": [],
        "table": [],
    }
    if daily.empty or weather is None or weather.data.empty:
        return unavailable

    def _normalize_date(val: Any) -> str:
        if hasattr(val, "strftime"):
            return val.strftime("%Y-%m-%d")
        text = str(val).strip()
        return text[:10]

    d_df = daily.copy()
    d_df["_date"] = d_df["日期"].apply(_normalize_date)

    w_df = weather.data.copy()
    w_df["_date"] = w_df["日期"].apply(_normalize_date)

    merged = pd.merge(d_df, w_df, on="_date", how="inner", suffixes=("", "_w"))
    if merged.empty:
        return unavailable

    merged = merged.sort_values("_date", ascending=True)

    def _to_num(s: pd.Series) -> pd.Series:
        return pd.to_numeric(s, errors="coerce").fillna(0.0)

    rev_col = "实收金额" if "实收金额" in merged.columns else "营业额"
    ord_col = "订单笔数" if "订单笔数" in merged.columns else ("订单数" if "订单数" in merged.columns else None)
    tkt_col = "客单价" if "客单价" in merged.columns else None

    merged["_rev"] = _to_num(merged[rev_col]) if rev_col in merged.columns else 0.0
    merged["_ord"] = _to_num(merged[ord_col]) if ord_col and ord_col in merged.columns else 0.0
    if tkt_col and tkt_col in merged.columns:
        merged["_tkt"] = _to_num(merged[tkt_col])
    else:
        merged["_tkt"] = merged.apply(lambda r: (r["_rev"] / r["_ord"]) if r["_ord"] > 0 else 0.0, axis=1)

    merged["_precip"] = _to_num(merged["降水量"]) if "降水量" in merged.columns else 0.0
    merged["_tmax"] = _to_num(merged["最高温"]) if "最高温" in merged.columns else 0.0
    merged["_tmin"] = _to_num(merged["最低温"]) if "最低温" in merged.columns else 0.0
    merged["_cond"] = merged["天气"].fillna("未知").astype(str)
    merged["_icon"] = merged["天气图标"].fillna("◌").astype(str)
    merged["_cat"] = merged["天气类型"].fillna("其他").astype(str)

    # 1. Timeline list
    timeline = []
    scatter = []
    table = []

    for _, r in merged.iterrows():
        date_str = str(r["_date"])
        rev = round(float(r["_rev"]), 2)
        orders = int(r["_ord"])
        ticket = round(float(r["_tkt"]), 2)
        precip = round(float(r["_precip"]), 1)
        tmax = round(float(r["_tmax"]), 1)
        tmin = round(float(r["_tmin"]), 1)
        cond = str(r["_cond"])
        icon = str(r["_icon"])
        cat = str(r["_cat"])

        item = {
            "date": date_str,
            "condition": cond,
            "category": cat,
            "icon": icon,
            "revenue": rev,
            "orders": orders,
            "ticket": ticket,
            "tempMax": tmax,
            "tempMin": tmin,
            "precipitation": precip,
        }
        timeline.append(item)
        scatter.append(item)
        table.append({
            "日期": date_str,
            "天气": f"{icon} {cond}",
            "最高温": tmax,
            "最低温": tmin,
            "降水量": precip,
            "实收金额": rev,
            "订单数": orders,
            "客单价": ticket,
        })

    # 2. By Condition aggregation
    cond_groups = []
    # Reference baseline: Sunny or Dry days
    sunny_rows = merged[merged["_cat"].isin(["晴", "晴朗", "多云"]) | (merged["_cond"].str.contains("晴"))]
    if not sunny_rows.empty:
        baseline_avg_rev = float(sunny_rows["_rev"].mean()) or 1.0
    else:
        baseline_avg_rev = float(merged["_rev"].mean()) or 1.0

    for cond, grp in merged.groupby("_cond"):
        days = len(grp)
        tot_rev = float(grp["_rev"].sum())
        avg_rev = float(grp["_rev"].mean())
        avg_ord = float(grp["_ord"].mean())
        avg_tkt = float(grp["_tkt"].mean())
        icon = str(grp["_icon"].iloc[0]) if not grp.empty else "◌"
        cat = str(grp["_cat"].iloc[0]) if not grp.empty else "其他"
        impact_pct = round(((avg_rev - baseline_avg_rev) / baseline_avg_rev) * 100, 1)

        cond_groups.append({
            "condition": str(cond),
            "category": cat,
            "icon": icon,
            "days": days,
            "totalRevenue": round(tot_rev, 2),
            "avgRevenue": round(avg_rev, 2),
            "avgOrders": round(avg_ord, 1),
            "avgTicket": round(avg_tkt, 2),
            "impactPct": impact_pct,
        })

    # Sort conditions by total revenue descending
    cond_groups.sort(key=lambda x: x["avgRevenue"], reverse=True)

    # 3. Rain vs Dry summary
    rain_mask = merged["_precip"] >= 0.1
    rain_df = merged[rain_mask]
    dry_df = merged[~rain_mask]

    rain_days = len(rain_df)
    dry_days = len(dry_df)
    total_days = len(merged)

    rain_avg_rev = float(rain_df["_rev"].mean()) if rain_days > 0 else 0.0
    dry_avg_rev = float(dry_df["_rev"].mean()) if dry_days > 0 else 0.0
    rain_avg_ord = float(rain_df["_ord"].mean()) if rain_days > 0 else 0.0
    dry_avg_ord = float(dry_df["_ord"].mean()) if dry_days > 0 else 0.0
    rain_avg_tkt = float(rain_df["_tkt"].mean()) if rain_days > 0 else 0.0
    dry_avg_tkt = float(dry_df["_tkt"].mean()) if dry_days > 0 else 0.0

    if dry_avg_rev > 0 and rain_days > 0:
        rain_impact_pct = round(((rain_avg_rev - dry_avg_rev) / dry_avg_rev) * 100, 1)
    else:
        rain_impact_pct = 0.0

    best_cond = cond_groups[0] if cond_groups else {}
    worst_cond = cond_groups[-1] if cond_groups else {}

    summary = {
        "totalDays": total_days,
        "rainDays": rain_days,
        "dryDays": dry_days,
        "rainAvgRevenue": round(rain_avg_rev, 2),
        "dryAvgRevenue": round(dry_avg_rev, 2),
        "rainAvgOrders": round(rain_avg_ord, 1),
        "dryAvgOrders": round(dry_avg_ord, 1),
        "rainAvgTicket": round(rain_avg_tkt, 2),
        "dryAvgTicket": round(dry_avg_tkt, 2),
        "rainImpactPct": rain_impact_pct,
        "bestCondition": best_cond,
        "worstCondition": worst_cond,
        "baselineAvgRevenue": round(baseline_avg_rev, 2),
    }

    return {
        "status": "available",
        "summary": summary,
        "byCondition": cond_groups,
        "timeline": timeline,
        "scatter": scatter,
        "table": table,
    }


def _build_ticket_type(sales_detail: pd.DataFrame) -> Dict[str, Any]:
    """Ticket type (堂食/外带/外送) split from sales_detail 类型 / 单据标签."""
    if sales_detail.empty:
        return {"types": [], "total": 0}
    type_col = None
    for cand in ("类型", "ticketType", "单据标签", "tag"):
        if cand in sales_detail.columns:
            type_col = cand
            break
    if not type_col:
        return {"types": [], "total": 0}
    grp = sales_detail.groupby(type_col, as_index=False).agg(
        单数=("流水号", "nunique") if "流水号" in sales_detail.columns else (type_col, "count"),
        实收金额=("实收金额", "sum") if "实收金额" in sales_detail.columns else (type_col, "count"),
    )
    total = float(grp["实收金额"].sum()) if "实收金额" in sales_detail.columns else 0
    items = [
        {
            "类型": str(r[type_col]),
            "单数": int(r["单数"]) if not pd.isna(r["单数"]) else 0,
            "实收金额": float(r["实收金额"]) if "实收金额" in sales_detail.columns and not pd.isna(r["实收金额"]) else 0,
            "占比": (float(r["实收金额"]) / total) if total and "实收金额" in sales_detail.columns else 0,
        }
        for _, r in grp.iterrows()
    ]
    items.sort(key=lambda x: -x["单数"])
    return {"types": items, "total": total}


def _profit_by_product(sales: pd.DataFrame) -> pd.DataFrame:
    """Top + bottom products by profit (requires 利润 or 成本 fields from PosPal)."""
    if sales.empty:
        return pd.DataFrame(columns=["商品名称", "商品分类", "收入分类", "实收金额", "销售数量", "利润", "利润率"])
    profit_col = "利润" if "利润" in sales.columns else None
    cost_col = "成本" if "成本" in sales.columns else None
    if not profit_col and not cost_col:
        return pd.DataFrame()
    grp_dict = {
        "实收金额": ("实收金额", "sum"),
    }
    if "销售数量" in sales.columns:
        grp_dict["销售数量"] = ("销售数量", "sum")
    if "流水号" in sales.columns:
        grp_dict["订单数"] = ("流水号", "nunique")
    if profit_col:
        grp_dict["利润"] = (profit_col, "sum")
    if cost_col:
        grp_dict["成本"] = (cost_col, "sum")
    grp = sales.groupby(["商品名称", "商品分类", "收入分类"], as_index=False).agg(**grp_dict)
    if "利润" not in grp.columns:
        grp["利润"] = grp["实收金额"] - grp.get("成本", 0)
    if "销售数量" not in grp.columns:
        grp["销售数量"] = 0
    if "订单数" not in grp.columns:
        grp["订单数"] = 0
    grp["利润率"] = (grp["利润"] / grp["实收金额"].replace(0, pd.NA)).fillna(0)
    return grp.sort_values("利润", ascending=False)


def _build_loss_by_reason(loss: pd.DataFrame) -> Dict[str, Any]:
    """Loss by reason, with quantity + amount, sorted by amount desc."""
    if loss.empty or "报损原因" not in loss.columns:
        return {"reasons": [], "totalAmount": 0, "totalQuantity": 0}
    tmp = loss.copy()
    tmp["报损原因"] = tmp["报损原因"].replace("", "未填写").fillna("未填写")
    grp = tmp.groupby("报损原因", as_index=False).agg(
        报损金额=("报损金额", "sum") if "报损金额" in tmp.columns else ("报废数量", "count"),
        报废数量=("报废数量", "sum") if "报废数量" in tmp.columns else ("报损金额", "count"),
    )
    if "报损金额" in grp.columns:
        grp = grp.sort_values("报损金额", ascending=False)
    items = [
        {
            "报损原因": str(r["报损原因"]),
            "报损金额": float(r["报损金额"]),
            "报废数量": int(r["报废数量"]) if not pd.isna(r["报废数量"]) else 0,
        }
        for _, r in grp.iterrows()
    ]
    return {
        "reasons": items,
        "totalAmount": float(grp["报损金额"].sum()) if "报损金额" in grp.columns else 0,
        "totalQuantity": int(grp["报废数量"].sum()) if "报废数量" in grp.columns else 0,
    }


def _build_member_summary(cards_detail: pd.DataFrame, cards: pd.DataFrame) -> Dict[str, Any]:
    """Member count + card balance from cards_detail (当前剩余金额) + cards aggregation."""
    member_count = 0
    if not cards_detail.empty and "会员卡号" in cards_detail.columns:
        member_count = int(cards_detail["会员卡号"].nunique())
    elif not cards_detail.empty and "卡号" in cards_detail.columns:
        member_count = int(cards_detail["卡号"].nunique())
    total_remaining = 0.0
    if not cards_detail.empty and "当前剩余金额" in cards_detail.columns:
        total_remaining = float(cards_detail["当前剩余金额"].sum())
    total_recharge = 0.0
    total_gift = 0.0
    if not cards_detail.empty:
        if "充值金额" in cards_detail.columns:
            total_recharge = float(cards_detail["充值金额"].sum())
        if "赠送金额" in cards_detail.columns:
            total_gift = float(cards_detail["赠送金额"].sum())
    return {
        "会员数": member_count,
        "剩余金额": total_remaining,
        "充值金额": total_recharge,
        "赠送金额": total_gift,
    }


def _build_card_balance(cards_detail: pd.DataFrame, cards: pd.DataFrame) -> Dict[str, Any]:
    """Card balance breakdown: 本金 vs 赠送."""
    principal = 0.0
    gift = 0.0
    if not cards.empty:
        if "本金消费金额" in cards.columns:
            principal = float(cards["本金消费金额"].sum())
        if "赠送消费金额" in cards.columns:
            gift = float(cards["赠送消费金额"].sum())
    return {
        "本金消费": principal,
        "赠送消费": gift,
        "本金赠送比": (principal / gift) if gift else 0,
    }


def _build_pospal_overview(
    sales: pd.DataFrame,
    sales_detail: pd.DataFrame,
    cards_detail: pd.DataFrame,
    query: DashboardQuery,
) -> Dict[str, Any]:
    """POS home-style overview metrics for the web API dashboard."""
    discounts = _build_discounts(sales, sales_detail)
    member_summary = _build_member_summary(cards_detail, pd.DataFrame())

    order_count = int(sales["流水号"].nunique()) if not sales.empty and "流水号" in sales.columns else 0
    revenue = float(sales["实收金额"].sum()) if not sales.empty and "实收金额" in sales.columns else 0.0
    gross_sales = float(sales["商品总价"].sum()) if not sales.empty and "商品总价" in sales.columns else revenue

    source_series = sales["来源"].fillna("") if not sales.empty and "来源" in sales.columns else pd.Series([], dtype=str)
    online_mask = source_series.astype(str).str.contains("美团|饿了么|抖音|外卖|小程序|网店|线上", regex=True, na=False)
    store_mask = ~online_mask if len(source_series) else pd.Series([], dtype=bool)

    store_sales = sales[store_mask] if not sales.empty and len(store_mask) == len(sales) else sales
    online_sales = sales[online_mask] if not sales.empty and len(online_mask) == len(sales) else pd.DataFrame()
    store_orders = int(store_sales["流水号"].nunique()) if not store_sales.empty and "流水号" in store_sales.columns else order_count
    online_orders = int(online_sales["流水号"].nunique()) if not online_sales.empty and "流水号" in online_sales.columns else 0

    dine_in_orders, takeaway_orders, other_orders = _split_ticket_modes(sales, sales_detail)
    hourly = _hourly_sales(sales)
    hourly_trend = []
    if not hourly.empty:
        hourly_trend = [
            {"小时": int(row["小时"]), "营业额": float(row["实收金额"]), "订单数": int(row["订单数"])}
            for _, row in hourly.iterrows()
        ]

    selected_preset = "month"
    if query.date_from and query.date_to:
        today = date.today().strftime("%Y-%m-%d")
        yday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        if query.date_from == today and query.date_to == today:
            selected_preset = "today"
        elif query.date_from == yday and query.date_to == yday:
            selected_preset = "yesterday"
        else:
            selected_preset = "week"
    return {
        "period": {
            "selected": selected_preset,
            "options": ["today", "yesterday", "week", "month"],
            "label": query.label(),
        },
        "business": {
            "营业实收": revenue,
            "销售金额": gross_sales,
            "销售金额退": 0.0,
            "订单总数": order_count,
            "堂食单数": dine_in_orders,
            "外卖单数": takeaway_orders,
            "其他单数": other_orders,
            "客单价": (revenue / order_count) if order_count else 0.0,
            "优惠金额": float(discounts.get("优惠金额", 0) or 0),
            "优惠单数": int(discounts.get("优惠单数", 0) or 0),
            "发券数量": 0,
            "券付单数": 0,
            "门店实收": float(store_sales["实收金额"].sum()) if not store_sales.empty and "实收金额" in store_sales.columns else revenue,
            "门店订单": store_orders,
        },
        "onlineStore": {
            "网店实收": float(online_sales["实收金额"].sum()) if not online_sales.empty and "实收金额" in online_sales.columns else 0.0,
            "支付订单": online_orders,
            "访客数量": None,
            "新增会员": int(member_summary.get("会员数", 0) or 0),
            "source": "derived_from_order_source",
        },
        "hourlyTrend": hourly_trend,
        "marketingCalendar": _build_marketing_calendar(query.year),
        "smsBalance": {
            "余额条数": None,
            "status": "unavailable",
            "message": "当前导出接口未返回短信余额",
        },
    }


def _split_ticket_modes(sales: pd.DataFrame, sales_detail: pd.DataFrame) -> tuple[int, int, int]:
    if sales.empty or "流水号" not in sales.columns:
        return 0, 0, 0

    by_order = sales.groupby("流水号").agg(
        来源=("来源", "first") if "来源" in sales.columns else ("流水号", "first"),
    )
    if not sales_detail.empty and "流水号" in sales_detail.columns:
        mode_cols = [col for col in ("类型", "单据标签", "备注", "来源") if col in sales_detail.columns]
        if mode_cols:
            detail_modes = (
                sales_detail.groupby("流水号")[mode_cols]
                .agg(lambda s: " ".join(str(v) for v in s.dropna().unique()))
                .apply(lambda row: " ".join(str(v) for v in row.values), axis=1)
            )
            by_order = by_order.join(detail_modes.rename("明细标签"), how="left")
    if "明细标签" not in by_order.columns:
        by_order["明细标签"] = ""

    text = (by_order["来源"].fillna("").astype(str) + " " + by_order["明细标签"].fillna("").astype(str))
    takeaway = text.str.contains("外卖|美团|饿了么|抖音|小程序|外带|打包|自提", regex=True, na=False)
    dine_in = text.str.contains("堂食|店内|门店", regex=True, na=False) & ~takeaway
    other = ~(takeaway | dine_in)
    return int(dine_in.sum()), int(takeaway.sum()), int(other.sum())


def _build_marketing_calendar(year: int) -> List[Dict[str, Any]]:
    today = date.today()
    events = [
        (date(year, 6, 18), "618购物节"),
        (date(year, 6, 19), "端午节"),
        (date(year, 8, 19), "七夕"),
    ]
    out = []
    for event_date, name in events:
        days_remaining = (event_date - today).days
        out.append({
            "日期": event_date.strftime("%m-%d"),
            "名称": name,
            "剩余天数": days_remaining,
            "status": "upcoming" if days_remaining >= 0 else "past",
        })
    return out


def _build_open_close_hours(sales: pd.DataFrame) -> Dict[str, Any]:
    """Detect when the store opens / closes + the 'shape' of the day curve."""
    if sales.empty or "小时" not in sales.columns:
        return {
            "openHour": 0, "closeHour": 0, "openAmount": 0, "closeAmount": 0,
            "ramp": 0, "wind": 0, "isOpen": False,
        }
    hourly = sales.groupby("小时", as_index=False).agg(
        订单数=("流水号", "nunique") if "流水号" in sales.columns else ("销售时间", "count"),
        实收金额=("实收金额", "sum"),
    ).sort_values("小时")
    if hourly.empty:
        return {
            "openHour": 0, "closeHour": 0, "openAmount": 0, "closeAmount": 0,
            "ramp": 0, "wind": 0, "isOpen": False,
        }
    # openHour = first hour with any sale
    open_row = hourly.iloc[0]
    close_row = hourly.iloc[-1]
    # peak hour
    peak_idx = int(hourly["实收金额"].idxmax())
    peak_hour = int(hourly.loc[peak_idx, "小时"])
    # ramp = minutes from open to peak, wind = minutes from peak to close
    open_hr = int(open_row["小时"])
    close_hr = int(close_row["小时"])
    ramp = max(0, (peak_hour - open_hr) * 60)
    wind = max(0, (close_hr - peak_hour) * 60)
    return {
        "openHour": open_hr,
        "closeHour": close_hr,
        "peakHour": peak_hour,
        "openAmount": float(open_row["实收金额"]),
        "closeAmount": float(close_row["实收金额"]),
        "ramp": ramp,
        "wind": wind,
        "isOpen": True,
    }


def _build_calendar(daily: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """Per-day revenue + profit + status for a calendar grid (date, revenue, profit, orders, lossRate, status)."""
    if daily.empty:
        return pd.DataFrame()
    out = []
    for _, row in daily.iterrows():
        rev = float(row.get("实收金额", 0) or 0)
        profit = float(row.get("净利润估算", 0) or 0)
        loss = float(row.get("损耗价值", 0) or 0)
        orders = float(row.get("订单笔数", 0) or 0)
        loss_rate = float(row.get("报损率", 0) or 0)
        status = "loss" if profit < 0 else ("warn" if loss_rate > 0.06 else ("idle" if rev == 0 else "ok"))
        out.append({
            "日期": str(row.get("日期")),
            "实收金额": rev,
            "净利润": profit,
            "订单数": orders,
            "报损率": loss_rate,
            "状态": status,
        })
    return pd.DataFrame(out)


def money(v: float) -> str:
    return f"¥{v:,.0f}"


# =============================================================================
# Statistical / multi-month helpers
# =============================================================================


def _build_volatility(daily: pd.DataFrame) -> Dict[str, Any]:
    """Variability metrics for the daily revenue series."""
    if daily.empty or "实收金额" not in daily.columns:
        return {
            "days": 0, "mean": 0, "median": 0, "std": 0, "cv": 0,
            "min": 0, "max": 0, "range": 0, "iqr": 0, "skewness": 0,
            "bestDay": None, "worstDay": None, "percentiles": {},
        }
    rev = pd.to_numeric(daily["实收金额"], errors="coerce").dropna()
    if rev.empty:
        return {
            "days": 0, "mean": 0, "median": 0, "std": 0, "cv": 0,
            "min": 0, "max": 0, "range": 0, "iqr": 0, "skewness": 0,
            "bestDay": None, "worstDay": None, "percentiles": {},
        }
    p = rev.quantile([0.10, 0.25, 0.5, 0.75, 0.90])
    best_idx = rev.idxmax()
    worst_idx = rev.idxmin()
    mean_v = float(rev.mean())
    std_v = float(rev.std(ddof=0))
    median_v = float(rev.median())
    min_v = float(rev.min())
    max_v = float(rev.max())
    skew = float((rev - mean_v).pow(3).mean() / (std_v ** 3)) if std_v else 0
    return {
        "days": int(len(rev)),
        "mean": mean_v,
        "median": median_v,
        "std": std_v,
        "cv": (std_v / mean_v) if mean_v else 0,
        "min": min_v,
        "max": max_v,
        "range": max_v - min_v,
        "iqr": float(p[0.75] - p[0.25]),
        "skewness": skew,
        "bestDay": {"date": str(daily.loc[best_idx, "日期"]), "value": float(rev.loc[best_idx])},
        "worstDay": {"date": str(daily.loc[worst_idx, "日期"]), "value": float(rev.loc[worst_idx])},
        "percentiles": {
            "P10": float(p[0.10]), "P25": float(p[0.25]),
            "P50": float(p[0.50]), "P75": float(p[0.75]), "P90": float(p[0.90]),
        },
    }


def _build_concentration(sales: pd.DataFrame) -> Dict[str, Any]:
    """Top-N concentration + Lorenz-style cumulative share curve."""
    if sales.empty or "实收金额" not in sales.columns or "商品名称" not in sales.columns:
        return {"total": 0, "skus": 0, "shares": [], "hhi": 0, "top5Share": 0, "top20Share": 0}
    grp = (
        sales.groupby("商品名称", as_index=False)["实收金额"].sum()
        .sort_values("实收金额", ascending=False)
    )
    total = float(grp["实收金额"].sum())
    if total <= 0:
        return {"total": 0, "skus": 0, "shares": [], "hhi": 0, "top5Share": 0, "top20Share": 0}
    grp["share"] = grp["实收金额"] / total
    grp["cumulative"] = grp["share"].cumsum()
    skus = len(grp)
    # Build coarse Lorenz curve at 10 quantile points so the chart stays small
    quantiles = [grp["cumulative"].iloc[max(0, int(skus * q) - 1)] if skus else 0 for q in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]]
    shares = [{"q": q, "share": float(s)} for q, s in zip([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], quantiles)]
    hhi = float((grp["share"] ** 2).sum())
    top5 = float(grp.head(5)["share"].sum())
    top20 = float(grp.head(min(20, skus))["share"].sum())
    return {
        "total": total,
        "skus": skus,
        "shares": shares,
        "hhi": hhi,
        "top5Share": top5,
        "top20Share": top20,
    }


def _category_by_hour(sales: pd.DataFrame) -> pd.DataFrame:
    """Income-category × hour cross-tab of revenue."""
    if sales.empty or "销售时间" not in sales.columns or "收入分类" not in sales.columns:
        return pd.DataFrame()
    df = sales.copy()
    df["小时"] = df["销售时间"].dt.hour
    pivot = df.pivot_table(
        index="收入分类", columns="小时", values="实收金额", aggfunc="sum", fill_value=0
    )
    # Reindex columns 0..23
    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]
    # Convert to long
    out = pivot.reset_index().melt(id_vars="收入分类", var_name="小时", value_name="实收金额")
    return out


def _order_amount_distribution(sales: pd.DataFrame) -> pd.DataFrame:
    """Bucket orders by total amount and return per-bucket stats."""
    if sales.empty or "流水号" not in sales.columns or "实收金额" not in sales.columns:
        return pd.DataFrame(columns=["区间", "订单数", "占比"])
    order_amounts = sales.groupby("流水号")["实收金额"].sum()
    bins = [0, 20, 40, 60, 80, 100, 150, 200, 300, float("inf")]
    labels = ["0–20", "20–40", "40–60", "60–80", "80–100", "100–150", "150–200", "200–300", "300+"]
    cats = pd.cut(order_amounts, bins=bins, labels=labels, right=False)
    counts = cats.value_counts().reindex(labels, fill_value=0)
    total = counts.sum() or 1
    return pd.DataFrame({
        "区间": labels,
        "订单数": counts.values,
        "占比": (counts.values / total),
    })


def _safe_head(df: pd.DataFrame, count: int) -> pd.DataFrame:
    return df.head(count).copy() if not df.empty else df.copy()


def _sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def _records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    safe = df.copy()
    for col in safe.columns:
        if pd.api.types.is_datetime64_any_dtype(safe[col]):
            safe[col] = safe[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            safe[col] = safe[col].map(_json_scalar)
    safe = safe.astype(object).where(pd.notna(safe), None)
    return safe.to_dict(orient="records")


def _json_scalar(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
