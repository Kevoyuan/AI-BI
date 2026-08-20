from pathlib import Path

import pandas as pd

from modules.dashboard_api import (
    DashboardQuery,
    _build_daily_summary,
    _build_payment_mix,
    _build_weather_daily,
    _subtract_recharges_from_payments,
    build_dashboard_payload,
)
from modules.pospal_live_data import LivePospalData
from modules.pospal_live_data import load_report_directory
from modules.weather_api import WeatherApiResult


def test_build_dashboard_payload_from_report_directory():
    report_dir = Path("data")
    if not (report_dir / "商品销售流水.xlsx").exists():
        return

    live = load_report_directory(report_dir)
    payload = build_dashboard_payload(live, DashboardQuery(year=2026, month=6))

    assert payload["meta"]["source"] == "银豹后台接口"
    assert payload["kpis"]["revenue"] > 0
    assert payload["incomeCategories"]
    assert payload["topProducts"]
    assert "sales" in payload["raw"]


def test_build_dashboard_payload_filters_custom_date_range():
    sales = pd.DataFrame(
        [
            _sale_row("2026-06-01 09:00:00", "A001", 100),
            _sale_row("2026-06-02 10:00:00", "A002", 200),
            _sale_row("2026-06-03 11:00:00", "A003", 300),
        ]
    )
    sales["销售时间"] = pd.to_datetime(sales["销售时间"])
    sales["日期"] = sales["销售时间"].dt.date
    sales["小时"] = sales["销售时间"].dt.hour

    loss = pd.DataFrame(
        [
            {"调整日期": pd.to_datetime("2026-06-01").date(), "报损金额": 10, "报废数量": 1, "报损原因": "过期", "商品分类": "面包", "商品名称": "吐司"},
            {"调整日期": pd.to_datetime("2026-06-02").date(), "报损金额": 20, "报废数量": 2, "报损原因": "过期", "商品分类": "面包", "商品名称": "吐司"},
        ]
    )
    cards = pd.DataFrame(
        [
            {"日期": pd.to_datetime("2026-06-01"), "充值总金额": 50, "储值卡消费总金额": 5, "本金消费金额": 5, "赠送消费金额": 0},
            {"日期": pd.to_datetime("2026-06-02"), "充值总金额": 80, "储值卡消费总金额": 8, "本金消费金额": 8, "赠送消费金额": 0},
        ]
    )
    cards_detail = pd.DataFrame(
        [
            {"日期": pd.to_datetime("2026-06-01").date(), "当前剩余金额": 500, "充值金额": 50, "赠送金额": 5},
            {"日期": pd.to_datetime("2026-06-02").date(), "当前剩余金额": 800, "充值金额": 80, "赠送金额": 8},
        ]
    )
    sales_detail = pd.DataFrame(
        [
            {"日期": pd.to_datetime("2026-06-01"), "流水号": "A001", "商品原价": 100, "实收金额": 100, "支付方式": "现金"},
            {"日期": pd.to_datetime("2026-06-02"), "流水号": "A002", "商品原价": 200, "实收金额": 200, "支付方式": "现金"},
        ]
    )

    payload = build_dashboard_payload(
        LivePospalData(
            sales=sales,
            loss=loss,
            cards=cards,
            cards_detail=cards_detail,
            sales_detail=sales_detail,
        ),
        DashboardQuery(year=2026, month=6, date_from="2026-06-02", date_to="2026-06-02"),
    )

    assert payload["meta"]["dateFrom"] == "2026-06-02"
    assert payload["meta"]["dateTo"] == "2026-06-02"
    assert payload["kpis"]["revenue"] == 200
    assert payload["kpis"]["orders"] == 1
    assert payload["kpis"]["loss"] == 20
    assert len(payload["daily"]) == 1
    assert payload["daily"][0]["日期"] == "2026-06-02"
    assert payload["raw"]["sales"][0]["流水号"] == "A002"
    assert payload["raw"]["cards"][0]["充值总金额"] == 80
    assert payload["raw"]["salesDetail"][0]["流水号"] == "A002"
    assert payload["paymentMix"]["reconciled"] is True
    assert payload["paymentMix"]["orderCount"] == 1


def test_payment_mix_includes_cashier_reconciliation_and_mixed_payments():
    sales = pd.DataFrame(
        [
            {"流水号": "A001", "实收金额": 100},
            {"流水号": "A002", "实收金额": 70},
        ]
    )
    payments = pd.DataFrame(
        [
            {"流水号": "A001", "支付方式": "微信", "金额": 60},
            {"流水号": "A001", "支付方式": "现金", "金额": 40},
            {"流水号": "A002", "支付方式": "微信", "金额": 70},
        ]
    )

    result = _build_payment_mix(payments, sales)

    assert result["status"] == "available"
    assert result["total"] == 170
    assert result["paymentCount"] == 3
    assert result["orderCount"] == 2
    assert result["mixedPaymentOrders"] == 1
    assert result["dominantMethod"] == "微信"
    assert result["reconciliationGap"] == 0
    assert result["reconciled"] is True
    assert result["methods"][0]["订单数"] == 2
    assert result["methods"][0]["平均每单"] == 65


def test_payment_summary_subtracts_recharge_payments_before_reconciliation():
    payments = pd.DataFrame(
        [
            {"日期": "2026-08-08", "支付方式": "微信/支付宝", "金额": 500, "支付笔数": 12},
            {"日期": "2026-08-08", "支付方式": "现金", "金额": 100, "支付笔数": 3},
        ]
    )
    recharge = pd.DataFrame(
        [
            {"日期": "2026-08-08", "支付分类": "微信/支付宝", "充值金额": 80},
            {"日期": "2026-08-08", "支付分类": "现金", "充值金额": 20},
        ]
    )

    result = _subtract_recharges_from_payments(payments, recharge)

    assert result["金额"].sum() == 500
    assert result["支付笔数"].sum() == 13
    assert result.set_index("支付方式").loc["微信/支付宝", "金额"] == 420


def test_daily_profit_ignores_operation_management_ratio():
    sales = pd.DataFrame(
        [
            {
                "日期": pd.Timestamp("2026-06-01").date(),
                "流水号": "A001",
                "实收金额": 1000,
                "商品总价": 1000,
                "销售数量": 10,
            }
        ]
    )

    daily = _build_daily_summary(
        sales,
        pd.DataFrame(),
        pd.DataFrame(),
        {"原料成本比": 0.4, "运营管理": 0.9, "固定支出": 100},
    )

    assert daily.loc[0, "净利润估算"] == 500
    assert "运营成本估算" not in daily.columns


def test_weather_daily_returns_history_without_income_analysis():
    weather_data = pd.DataFrame(
        [
            {
                "日期": pd.Timestamp("2026-08-07").date(),
                "天气": "晴",
                "天气类型": "晴朗",
                "天气图标": "☀",
                "平均温度": 30,
                "最高温": 34,
                "最低温": 26,
                "降水量": 0,
                "降雨量": 0,
                "降水时长": 0,
                "日照时长": 10,
                "最大风速": 16,
                "数据类型": "历史再分析",
            },
            {
                "日期": pd.Timestamp("2026-08-08").date(),
                "天气": "中雨",
                "天气类型": "中雨",
                "天气图标": "🌧",
                "平均温度": 27,
                "最高温": 31,
                "最低温": 24,
                "降水量": 18,
                "降雨量": 17,
                "降水时长": 5,
                "日照时长": 3.5,
                "最大风速": 22,
            },
        ]
    )
    result = _build_weather_daily(
        WeatherApiResult(
            data=weather_data,
            status="available",
            message="已获取虎门今日天气",
        ),
    )

    assert result["status"] == "available"
    assert result["latest"]["date"] == "2026-08-08"
    assert result["latest"]["condition"] == "中雨"
    assert result["latest"]["temperatureMax"] == 31
    assert result["latest"]["precipitation"] == 18
    assert result["latest"]["windSpeedMax"] == 22
    assert len(result["days"]) == 2
    assert result["days"][1]["date"] == "2026-08-07"
    assert "analysis" not in result
    assert "rainComparison" not in result
    assert "correlations" not in result


def test_build_weather_sales_correlation():
    from modules.dashboard_api import _build_weather_sales

    daily = pd.DataFrame(
        [
            {"日期": "2026-08-07", "实收金额": 1000.0, "订单笔数": 40, "客单价": 25.0},
            {"日期": "2026-08-08", "实收金额": 800.0, "订单笔数": 32, "客单价": 25.0},
        ]
    )
    weather_data = pd.DataFrame(
        [
            {
                "日期": pd.to_datetime("2026-08-07").date(),
                "天气": "晴",
                "天气类型": "晴朗",
                "天气图标": "☀",
                "最高温": 34.0,
                "最低温": 26.0,
                "降水量": 0.0,
            },
            {
                "日期": pd.to_datetime("2026-08-08").date(),
                "天气": "中雨",
                "天气类型": "中雨",
                "天气图标": "🌧",
                "最高温": 30.0,
                "最低温": 24.0,
                "降水量": 15.5,
            },
        ]
    )
    weather = WeatherApiResult(
        data=weather_data,
        status="available",
        message="已获取虎门天气",
    )

    res = _build_weather_sales(daily, weather)
    assert res["status"] == "available"
    assert res["summary"]["totalDays"] == 2
    assert res["summary"]["rainDays"] == 1
    assert res["summary"]["dryDays"] == 1
    assert res["summary"]["dryAvgRevenue"] == 1000.0
    assert res["summary"]["rainAvgRevenue"] == 800.0
    assert res["summary"]["rainImpactPct"] == -20.0
    assert len(res["byCondition"]) == 2
    assert len(res["timeline"]) == 2
    assert len(res["scatter"]) == 2
    assert len(res["table"]) == 2


def _sale_row(sold_at: str, order_id: str, amount: float) -> dict:
    return {
        "销售时间": sold_at,
        "流水号": order_id,
        "收入分类": "面包",
        "商品分类": "面包",
        "来源": "门店",
        "商品名称": "吐司",
        "销售数量": 1,
        "商品总价": amount,
        "实收金额": amount,
        "商品原价": amount,
        "成本": amount * 0.4,
        "利润": amount * 0.6,
    }
