"""Unit tests for Market Basket Analysis and Hourly Traffic Analysis."""

import sys
import pandas as pd
import pytest

sys.path.insert(0, ".")

from skills.deep_analysis.scripts.basket_analysis import analyze_basket_cross_sell
from skills.deep_analysis.scripts.hourly_traffic import analyze_hourly_traffic
from modules.analysis_tools import run_basket_analysis, run_hourly_traffic
from modules.ai_assistant import run_analysis


def test_basket_analysis_empty():
    res = analyze_basket_cross_sell(pd.DataFrame())
    assert "error" in res
    assert res["attachment_rate"] == 0.0


def test_basket_analysis_pairs():
    # Construct 4 transactions:
    # T1: 生吐司, 草莓果酱, 拿铁
    # T2: 生吐司, 草莓果酱
    # T3: 生吐司, 可颂
    # T4: 拿铁
    data = [
        {"流水号": "T1", "商品名称": "招牌生吐司", "销售数量": 1, "实收金额": 28.0},
        {"流水号": "T1", "商品名称": "草莓果酱", "销售数量": 1, "实收金额": 15.0},
        {"流水号": "T1", "商品名称": "冰拿铁", "销售数量": 1, "实收金额": 18.0},
        {"流水号": "T2", "商品名称": "招牌生吐司", "销售数量": 1, "实收金额": 28.0},
        {"流水号": "T2", "商品名称": "草莓果酱", "销售数量": 1, "实收金额": 15.0},
        {"流水号": "T3", "商品名称": "招牌生吐司", "销售数量": 1, "实收金额": 28.0},
        {"流水号": "T3", "商品名称": "原味可颂", "销售数量": 1, "实收金额": 12.0},
        {"流水号": "T4", "商品名称": "冰拿铁", "销售数量": 1, "实收金额": 18.0},
    ]
    df = pd.DataFrame(data)
    res = analyze_basket_cross_sell(df, min_support_count=2)
    assert res["total_transactions"] == 4
    # Total items = 8, transactions = 4 -> attachment rate = 2.0
    assert res["attachment_rate"] == 2.0
    assert res["multi_item_ratio"] == "75.0%"

    # Top pair should be (招牌生吐司, 草莓果酱) with count 2
    assert len(res["top_pairs"]) > 0
    top = res["top_pairs"][0]
    assert "招牌生吐司" in (top["item_a"], top["item_b"])
    assert "草莓果酱" in (top["item_a"], top["item_b"])
    assert top["co_occurrence"] == 2


def test_basket_analysis_target_product():
    data = [
        {"流水号": "T1", "商品名称": "招牌生吐司", "销售数量": 1, "实收金额": 28.0},
        {"流水号": "T1", "商品名称": "草莓果酱", "销售数量": 1, "实收金额": 15.0},
        {"流水号": "T2", "商品名称": "招牌生吐司", "销售数量": 1, "实收金额": 28.0},
        {"流水号": "T2", "商品名称": "草莓果酱", "销售数量": 1, "实收金额": 15.0},
        {"流水号": "T3", "商品名称": "招牌生吐司", "销售数量": 1, "实收金额": 28.0},
        {"流水号": "T3", "商品名称": "原味可颂", "销售数量": 1, "实收金额": 12.0},
    ]
    df = pd.DataFrame(data)
    res = analyze_basket_cross_sell(df, target_product="生吐司", min_support_count=1)
    assert res["target_product"] == "招牌生吐司"
    assert res["target_sales_count"] == 3
    assert len(res["top_pairs"]) == 2
    assert res["top_pairs"][0]["item_b"] == "草莓果酱"
    assert res["top_pairs"][0]["confidence"] == "66.7%"


def test_hourly_traffic_empty():
    res = analyze_hourly_traffic(pd.DataFrame())
    assert "error" in res


def test_hourly_traffic_stats():
    data = [
        {"销售时间": "2026-08-10 08:15:00", "小时": 8, "实收金额": 50.0, "流水号": "T1"},
        {"销售时间": "2026-08-10 08:45:00", "小时": 8, "实收金额": 30.0, "流水号": "T2"},
        {"销售时间": "2026-08-10 12:30:00", "小时": 12, "实收金额": 120.0, "流水号": "T3"},
        {"销售时间": "2026-08-10 18:30:00", "小时": 18, "实收金额": 200.0, "流水号": "T4"},
    ]
    df = pd.DataFrame(data)
    res = analyze_hourly_traffic(df)
    assert res["total_revenue"] == 400.0
    assert res["total_orders"] == 4
    assert res["overall_ac"] == 100.0
    assert res["golden_hour"]["hour"] == "18:00"
    assert res["golden_hour"]["revenue"] == 200.0
    assert "peaks" in res
    assert res["peaks"]["morning"]["label"] == "早高峰(07:00-09:00)"
    assert res["peaks"]["morning"]["total_revenue"] == 80.0


def test_run_analysis_dispatch():
    # Test dispatching invalid analysis raises error
    with pytest.raises(ValueError, match="analysis 必须是"):
        run_analysis.invoke({"analysis": "invalid_type"})
