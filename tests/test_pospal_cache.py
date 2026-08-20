"""Tests for the PosPal disk cache (v2 parquet + archive pinning).

These cover the cache layer only — network downloads are monkeypatched.
Run inside the project venv (needs pyarrow for parquet I/O).
"""
import pickle
import sys
import time

import pandas as pd
import pytest

sys.path.insert(0, ".")

from modules.pospal_live_data import (  # noqa: E402
    LivePospalData,
    _download_month,
    _load_disk_cache,
    _save_disk_cache,
    _legacy_pickle_path,
    archive_month,
    fetch_live_pospal_data,
    invalidate_month_cache,
    monthly_cache_size,
)


def _sample_live() -> LivePospalData:
    return LivePospalData(
        sales=pd.DataFrame(
            {"销售时间": pd.to_datetime(["2026-03-01 10:00"]), "实收金额": [100.0]}
        ),
        loss=pd.DataFrame(
            {"审核时间": pd.to_datetime(["2026-03-02"]), "报损金额": [5.0]}
        ),
        cards=pd.DataFrame(
            {"日期": pd.to_datetime(["2026-03-03"]), "充值总金额": [50.0]}
        ),
        cards_detail=pd.DataFrame(),  # deliberately empty frame
        sales_detail=pd.DataFrame({"流水号": ["A1"], "实收金额": [100.0]}),
        payments=pd.DataFrame({"日期": pd.to_datetime(["2026-03-05"]), "金额": [30.0]}),
    )


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point REPORT_CACHE_DIR and PROJECT_ROOT at a temp dir and reset the in-memory cache."""
    monkeypatch.setattr("modules.pospal_live_data.REPORT_CACHE_DIR", tmp_path)
    monkeypatch.setattr("modules.pospal_live_data.PROJECT_ROOT", tmp_path)
    invalidate_month_cache()
    assert monthly_cache_size() == 0
    yield
    invalidate_month_cache()


def _count_downloads(monkeypatch, live):
    calls = {"n": 0}

    def fake_download(year, month):
        calls["n"] += 1
        return live

    monkeypatch.setattr("modules.pospal_live_data._download_month", fake_download)
    return calls


def test_parquet_roundtrip(tmp_path, monkeypatch):
    live = _sample_live()
    _save_disk_cache(2026, 3, 1234.0, live, archived=True)
    assert (tmp_path / "2026-03" / "meta.json").exists()
    assert (tmp_path / "2026-03" / "sales.parquet").exists()

    got = _load_disk_cache(2026, 3)
    assert got is not None
    cached_at, loaded, archived = got
    assert cached_at == 1234.0
    assert archived is True
    assert len(loaded.sales) == 1
    assert loaded.sales["实收金额"].iloc[0] == 100.0
    assert len(loaded.loss) == 1
    assert loaded.cards_detail.empty  # empty frame round-trips


def test_legacy_pickle_lazily_migrates(tmp_path):
    live = _sample_live()
    legacy = _legacy_pickle_path(2026, 4)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    with legacy.open("wb") as handle:
        pickle.dump({"version": 1, "cached_at": 999.0, "live": live}, handle)

    got = _load_disk_cache(2026, 4)
    assert got is not None
    cached_at, loaded, archived = got
    assert cached_at == 999.0
    assert archived is False  # not in archive list → not pinned
    # migrated: parquet dir exists, legacy pickle removed
    assert (tmp_path / "2026-04" / "meta.json").exists()
    assert not legacy.exists()


def test_archive_pins_month_and_skips_ttl(tmp_path, monkeypatch):
    live = _sample_live()
    calls = _count_downloads(monkeypatch, live)

    assert archive_month(2026, 5) is True
    assert calls["n"] == 1  # first archive fetches once
    _, _l, archived = _load_disk_cache(2026, 5)
    assert archived is True

    # archived month, very old cache → still served, no re-download
    invalidate_month_cache()
    fetch_live_pospal_data(2026, 5)
    assert calls["n"] == 1


def test_archived_force_refresh_escape_hatch(tmp_path, monkeypatch):
    """Archived + force_refresh still re-downloads once past the 30d floor."""
    live = _sample_live()
    calls = _count_downloads(monkeypatch, live)

    # seed an archived cache that is 40 days old (> 30d historical TTL)
    _save_disk_cache(2026, 6, time.time() - 40 * 86400, live, archived=True)
    invalidate_month_cache()

    fetch_live_pospal_data(2026, 6)  # normal read → archive wins
    assert calls["n"] == 0

    fetch_live_pospal_data(2026, 6, force_refresh=True)  # past floor → refresh
    assert calls["n"] == 1


def test_archive_second_call_no_redownload(tmp_path, monkeypatch):
    live = _sample_live()
    calls = _count_downloads(monkeypatch, live)
    archive_month(2026, 7)
    archive_month(2026, 7)
    assert calls["n"] == 1


def test_parquet_handles_mixed_object_column(tmp_path):
    """PosPal 导出列（如 充值环比增长率）混合数字与 '-' 占位符，pyarrow 必须能写入。"""
    live = _sample_live()
    live.cards = pd.DataFrame(
        {
            "日期": pd.to_datetime(["2026-03-03", "2026-03-04", "2026-03-05"]),
            "充值总金额": [50.0, 60.0, 70.0],
            "充值环比增长率": ["5.2", "-", "3.1"],  # mixed float/str
            "备注": ["无", "补货", None],  # pure text with NaN
        }
    )

    _save_disk_cache(2026, 8, 111.0, live)
    assert (tmp_path / "2026-08" / "meta.json").exists()

    got = _load_disk_cache(2026, 8)
    assert got is not None
    _, loaded, _archived = got
    # '-' placeholder survives the round-trip (as string), numeric stays numeric
    values = list(loaded.cards["充值环比增长率"])
    assert "-" in values
    assert loaded.cards["备注"].notna().sum() == 2
    assert loaded.cards["充值总金额"].iloc[0] == 50.0  # numeric column intact


def test_migration_keeps_legacy_pickle_on_save_failure(tmp_path, monkeypatch):
    """迁移失败（parquet 写不了）时不能删除唯一的旧 pickle 副本。"""
    live = _sample_live()
    legacy = _legacy_pickle_path(2026, 9)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    with legacy.open("wb") as handle:
        pickle.dump({"version": 1, "cached_at": 888.0, "live": live}, handle)

    # make every parquet write fail
    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("modules.pospal_live_data._parquet_safe_frame", boom)

    got = _load_disk_cache(2026, 9)
    assert got is not None  # still served from the legacy pickle
    assert legacy.exists()  # legacy copy preserved despite save failure
