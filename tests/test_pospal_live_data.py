from pathlib import Path

import pandas as pd

from modules import pospal_live_data
from modules.pospal_live_data import load_report_directory


def test_load_report_directory_parses_current_exports():
    report_dir = Path("data")
    if not (report_dir / "商品销售流水.xlsx").exists():
        return

    live = load_report_directory(report_dir)
    assert not live.sales.empty
    assert {"收入分类", "来源", "日期", "小时"}.issubset(live.sales.columns)
    assert pd.api.types.is_numeric_dtype(live.sales["实收金额"])
    assert pd.api.types.is_numeric_dtype(live.sales["销售数量"])
    assert "日期" in live.cards.columns


def test_monthly_cache_returns_deep_copy_and_force_refresh(monkeypatch, tmp_path):
    """The (year, month) cache should return a deep-copy clone and
    force_refresh=True should drop the entry."""
    monkeypatch.setattr(pospal_live_data, "REPORT_CACHE_DIR", tmp_path / "month-cache")
    monkeypatch.setattr(pospal_live_data, "MIN_FORCE_REFRESH_INTERVAL_SECONDS", 0)
    pospal_live_data.invalidate_month_cache()
    assert pospal_live_data.monthly_cache_size() == 0

    sample = pospal_live_data.LivePospalData(
        sales=pd.DataFrame({"实收金额": [1.0, 2.0]}),
        loss=pd.DataFrame({"报损金额": [0.0]}),
        cards=pd.DataFrame({"充值总金额": [0.0]}),
        cards_detail=pd.DataFrame({"充值金额": [0.0]}),
        sales_detail=pd.DataFrame({"实收金额": [0.0]}),
    )

    # Stub out the real download so we don't hit PosPal from a unit test.
    downloads = {"count": 0}

    def fake_download(year, month):
        downloads["count"] += 1
        return sample

    monkeypatch.setattr(pospal_live_data, "_download_month", fake_download)

    first = pospal_live_data.fetch_live_pospal_data(2099, 1)
    second = pospal_live_data.fetch_live_pospal_data(2099, 1)
    assert downloads["count"] == 1
    assert pospal_live_data.monthly_cache_size() == 1

    # The returned frames are decoupled from the cache (mutations must not leak).
    first.sales["实收金额"] = first.sales["实收金额"] * 10
    assert (second.sales["实收金额"] == sample.sales["实收金额"]).all()

    # force_refresh bypasses the cache and re-downloads.
    pospal_live_data.fetch_live_pospal_data(2099, 1, force_refresh=True)
    assert downloads["count"] == 2

    # Targeted invalidation removes just the specified month.
    pospal_live_data.fetch_live_pospal_data(2099, 1)
    pospal_live_data.fetch_live_pospal_data(2099, 2)
    assert pospal_live_data.monthly_cache_size() == 2
    assert pospal_live_data.invalidate_month_cache(2099, 1) == 1
    assert pospal_live_data.monthly_cache_size() == 1
    assert pospal_live_data.invalidate_month_cache() == 1
    assert pospal_live_data.monthly_cache_size() == 0


def test_persistent_cache_survives_restart_and_enforces_refresh_floor(monkeypatch, tmp_path):
    pospal_live_data.invalidate_month_cache()
    monkeypatch.setattr(pospal_live_data, "REPORT_CACHE_DIR", tmp_path / "month-cache")
    monkeypatch.setattr(pospal_live_data, "MIN_FORCE_REFRESH_INTERVAL_SECONDS", 3600)

    sample = pospal_live_data.LivePospalData(
        sales=pd.DataFrame({"实收金额": [8.0]}),
        loss=pd.DataFrame(),
        cards=pd.DataFrame(),
        cards_detail=pd.DataFrame(),
        sales_detail=pd.DataFrame(),
    )
    downloads = {"count": 0}

    def fake_download(year, month):
        downloads["count"] += 1
        return sample

    monkeypatch.setattr(pospal_live_data, "_download_month", fake_download)

    first = pospal_live_data.fetch_live_pospal_data(2099, 3)
    pospal_live_data.invalidate_month_cache()
    second = pospal_live_data.fetch_live_pospal_data(2099, 3, force_refresh=True)

    assert downloads["count"] == 1
    assert first.sales.equals(second.sales)
    # v2 cache format: per-month directory with parquet frames + meta.json
    cache_dir = tmp_path / "month-cache" / "2099-03"
    assert cache_dir.is_dir()
    assert (cache_dir / "meta.json").exists()
    assert (cache_dir / "sales.parquet").exists()
