"""Regression tests for the bllz-derived single-product analysis path."""
from datetime import date

import pandas as pd

from modules import analysis_tools as tools


def test_resolve_window_month_range():
    start, end = tools.resolve_window("2026-08~2026-09")
    assert start == date(2026, 8, 1)
    assert end == date(2026, 9, 30)


def test_query_product_sales_merges_barcode_aliases(monkeypatch):
    sales = pd.DataFrame(
        [
            {
                "流水号": "A1",
                "商品名称": "经典生吐司",
                "商品条码": "SKU-001",
                "销售数量": 2,
                "实收金额": 40.0,
                "利润": 12.0,
                "日期": date(2026, 8, 2),
            },
            {
                "流水号": "A2",
                "商品名称": "生吐司（新包装）",
                "商品条码": "SKU-001",
                "销售数量": 3,
                "实收金额": 63.0,
                "利润": 18.0,
                "日期": date(2026, 9, 3),
            },
            {
                "流水号": "B1",
                "商品名称": "全麦吐司",
                "商品条码": "SKU-002",
                "销售数量": 5,
                "实收金额": 75.0,
                "利润": 20.0,
                "日期": date(2026, 9, 4),
            },
        ]
    )
    loss = pd.DataFrame(
        [
            {
                "商品名称": "生吐司（新包装）",
                "商品条码": "SKU-001",
                "报废数量": 1,
                "报损金额": 21.0,
                "报损原因": "过期",
                "日期": date(2026, 9, 5),
            }
        ]
    )

    monkeypatch.setattr(tools, "_fetch_sales_full_window", lambda _s, _e: sales.copy())
    monkeypatch.setattr(tools, "_fetch_loss_full_window", lambda _s, _e: loss.copy())

    result = tools.query_product_sales("经典生吐司", "2026-08~2026-09")

    assert result["found"] is True
    assert result["total_quantity"] == 5
    assert result["total_revenue"] == 103.0
    assert result["order_count"] == 2
    assert result["has_name_alias"] is True
    assert {item["name"] for item in result["name_breakdown"]} == {
        "经典生吐司",
        "生吐司（新包装）",
    }
    assert [item["month"] for item in result["monthly_breakdown"]] == [
        "2026-08",
        "2026-09",
    ]
    assert result["loss_summary"]["total_quantity"] == 1
    assert result["loss_summary"]["total_amount"] == 21.0


def test_query_product_sales_empty_name():
    result = tools.query_product_sales("")
    assert "error" in result
