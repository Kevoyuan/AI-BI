"""Live PosPal data loader for the primary Web Dashboard.

The loader fetches reports through the PosPal web backend API into a temporary
directory, parses the returned Excel files, and returns cleaned DataFrames. It
does not create or read monthly SQLite databases. The legacy Streamlit API
Dashboard reuses this module only for compatibility.

Caching (saves PosPal quota):
* in-memory cache keyed by (year, month), plus a persistent disk cache at
  ``.cache/pospal-months/YYYY-MM/`` (parquet frames + meta.json, format v2).
* TTL: 6h for the current month, 30 days for closed months; ``force_refresh``
  cannot bypass a 6h minimum floor (free-quota protection); on download
  failure the stale local copy is used.
* Months can be archived (``archive_month`` / ``POSPAL_ARCHIVE_MONTHS``) so
  they never expire — long-term data for cross-period comparisons.
* Legacy v1 pickles (``YYYY-MM.pickle``) are still read and lazily migrated.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

import data_scrapy
from modules.pospal_openapi import classify_income, normalize_payment_category
from modules.pospal_webapi import download_reports_via_webapi
from modules.privacy import sanitize_live_data


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class LivePospalData:
    sales: pd.DataFrame
    loss: pd.DataFrame
    cards: pd.DataFrame
    cards_detail: pd.DataFrame
    sales_detail: pd.DataFrame
    payments: pd.DataFrame = field(default_factory=pd.DataFrame)
    source: str = "unknown"


# (year, month) -> (cached_at_epoch, LivePospalData, archived_flag).
_MONTHLY_CACHE: Dict[Tuple[int, int], Tuple[float, LivePospalData, bool]] = {}
_DOWNLOAD_LOCK = threading.RLock()

# The HTML dashboard is read-heavy. Current-month data may be refreshed at most
# every six hours, while closed months remain reusable for 30 days. The same
# limits apply across process restarts through the persistent cache below.
MONTHLY_CACHE_TTL_SECONDS = int(
    os.environ.get("POSPAL_CURRENT_MONTH_CACHE_TTL", str(6 * 60 * 60))
)
HISTORICAL_CACHE_TTL_SECONDS = int(
    os.environ.get("POSPAL_HISTORICAL_CACHE_TTL", str(30 * 24 * 60 * 60))
)
MIN_FORCE_REFRESH_INTERVAL_SECONDS = int(
    os.environ.get("POSPAL_MIN_REFRESH_INTERVAL", str(6 * 60 * 60))
)
REPORT_CACHE_DIR = Path(
    os.environ.get(
        "POSPAL_REPORT_CACHE_DIR",
        str(PROJECT_ROOT / ".cache" / "pospal-months"),
    )
).expanduser()
# Cache format v2: one directory per month (parquet frames + meta.json).
# Legacy v1 pickles at <dir>/YYYY-MM.pickle are still read and lazily migrated.
CACHE_FORMAT_VERSION = 2

# LivePospalData attribute names persisted to parquet files.
_LIVE_FIELDS = ("sales", "loss", "cards", "cards_detail", "sales_detail", "payments")


def _parse_archive_months(raw: str) -> set:
    """Parse a "2025-01,2025-03" env list into {(year, month)}."""
    months = set()
    for token in (raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            y, m = token.split("-")
            months.add((int(y), int(m)))
        except (ValueError, TypeError):
            continue
    return months


# Months pinned forever (never expire) via POSPAL_ARCHIVE_MONTHS env.
_ARCHIVE_MONTHS = _parse_archive_months(os.environ.get("POSPAL_ARCHIVE_MONTHS", ""))


def _clone_live(live: LivePospalData) -> LivePospalData:
    """Return a deep copy of the cached DataFrames so callers can filter freely."""
    return LivePospalData(
        sales=live.sales.copy(deep=True),
        loss=live.loss.copy(deep=True),
        cards=live.cards.copy(deep=True),
        cards_detail=live.cards_detail.copy(deep=True),
        sales_detail=live.sales_detail.copy(deep=True),
        payments=live.payments.copy(deep=True),
        source=getattr(live, "source", "unknown"),
    )


def _download_month(year: int, month: int) -> LivePospalData:
    with tempfile.TemporaryDirectory(prefix="pospal-live-") as tmp_dir:
        session = data_scrapy.login_session(max_retries=1)
        download_reports_via_webapi(
            session,
            data_scrapy.BASE_URL,
            data_scrapy.HEADERS,
            tmp_dir,
            year,
            month,
        )
        live = load_report_directory(Path(tmp_dir))
        live.source = "live_api"
        return live


def fetch_live_pospal_data(
    year: int, month: int, *, force_refresh: bool = False
) -> LivePospalData:
    """Fetch and parse a month of PosPal data without creating a database.

    The (year, month) bundle is memoised in process memory; subsequent calls
    within MONTHLY_CACHE_TTL_SECONDS return a deep-copied clone so callers can
    filter and mutate without poisoning the cache. Pass force_refresh=True
    (typically wired to a user-driven "刷新" button) to drop the cached entry
    and re-download.
    """
    key = (year, month)
    with _DOWNLOAD_LOCK:
        now = time.time()
        cached = _MONTHLY_CACHE.get(key)
        disk_cached = _load_disk_cache(year, month)
        if disk_cached and (cached is None or disk_cached[0] > cached[0]):
            cached = disk_cached
            _MONTHLY_CACHE[key] = disk_cached

        if cached is not None:
            cached_at, live, archived = cached
            # Also protect entries inserted by older processes before the
            # privacy boundary was introduced.
            live = sanitize_live_data(live)
            cached = (cached_at, live, archived)
            _MONTHLY_CACHE[key] = cached
            age = max(now - cached_at, 0)
            # Archived months are pinned: never expire on normal reads, and
            # even force_refresh cannot bypass the free-quota floor.
            if archived and not force_refresh:
                return _clone_live(live)
            normal_ttl = _cache_ttl_seconds(year, month)
            refresh_floor = max(
                MIN_FORCE_REFRESH_INTERVAL_SECONDS,
                normal_ttl if _is_closed_month(year, month) else 0,
            )
            if (not force_refresh and age < normal_ttl) or (
                force_refresh and age < refresh_floor
            ):
                return _clone_live(live)

        try:
            live = sanitize_live_data(_download_month(year, month))
        except Exception:
            if cached is not None:
                logger.exception(
                    "银豹月报刷新失败，使用本地陈旧缓存: %04d-%02d", year, month
                )
                return _clone_live(cached[1])
            raise

        cached_at = time.time()
        archived = (year, month) in _ARCHIVE_MONTHS
        _MONTHLY_CACHE[key] = (cached_at, live, archived)
        _save_disk_cache(year, month, cached_at, live, archived=archived)
        return _clone_live(live)


def _is_closed_month(year: int, month: int) -> bool:
    today = date.today()
    return (year, month) < (today.year, today.month)


def _cache_ttl_seconds(year: int, month: int) -> int:
    return (
        HISTORICAL_CACHE_TTL_SECONDS
        if _is_closed_month(year, month)
        else MONTHLY_CACHE_TTL_SECONDS
    )


def _disk_cache_path(year: int, month: int) -> Path:
    """v2 cache layout: one directory per month (parquet frames + meta.json)."""
    return REPORT_CACHE_DIR / f"{year:04d}-{month:02d}"


def _legacy_pickle_path(year: int, month: int) -> Path:
    return REPORT_CACHE_DIR / f"{year:04d}-{month:02d}.pickle"


def _load_disk_cache(
    year: int, month: int
) -> Tuple[float, LivePospalData, bool] | None:
    """Load a month bundle from disk (v2 parquet first, then legacy v1 pickle).

    Legacy pickles are lazily migrated to the parquet layout — the data is
    re-saved in the new format without any extra PosPal download.
    Returns ``(cached_at, live, archived)`` or ``None``.
    """
    cached = _load_parquet_cache(year, month)
    if cached is not None:
        return cached
    legacy = _load_legacy_pickle(year, month)
    if legacy is None:
        return None
    cached_at, live = legacy
    live = sanitize_live_data(live)
    live.source = "disk_cache"
    archived = (year, month) in _ARCHIVE_MONTHS
    if _save_disk_cache(year, month, cached_at, live, archived=archived):
        # Only drop the legacy pickle once the parquet copy is safely on disk.
        try:
            _legacy_pickle_path(year, month).unlink(missing_ok=True)
        except OSError:
            pass
    return cached_at, live, archived


def _load_parquet_cache(
    year: int, month: int
) -> Tuple[float, LivePospalData, bool] | None:
    candidate_dirs = [
        REPORT_CACHE_DIR / f"{year:04d}-{month:02d}",
        PROJECT_ROOT / "prewarmed_cache" / "pospal-months" / f"{year:04d}-{month:02d}",
        PROJECT_ROOT / ".cache" / "pospal-months" / f"{year:04d}-{month:02d}",
    ]
    for path in candidate_dirs:
        meta_path = path / "meta.json"
        if not (path.exists() and meta_path.exists()):
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("version") != CACHE_FORMAT_VERSION:
                continue
            frames = {
                field: pd.read_parquet(path / f"{field}.parquet") for field in _LIVE_FIELDS
            }
            live = sanitize_live_data(
                LivePospalData(
                    **frames,
                    source=(
                        "prewarmed_cache"
                        if "prewarmed_cache" in str(path)
                        else "disk_cache"
                    ),
                )
            )
            return float(meta["cached_at"]), live, bool(meta.get("archived", False))
        except Exception:
            logger.warning("忽略无法读取的银豹月报缓存: %s", path, exc_info=True)
            continue
    return None


def _load_legacy_pickle(
    year: int, month: int
) -> Tuple[float, LivePospalData] | None:
    path = _legacy_pickle_path(year, month)
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        if payload.get("version") != 1:
            return None
        live = payload.get("live")
        if not isinstance(live, LivePospalData):
            return None
        return float(payload["cached_at"]), live
    except (OSError, EOFError, pickle.PickleError, AttributeError, KeyError, ValueError):
        logger.warning("忽略无法读取的银豹月报缓存: %s", path, exc_info=True)
        return None


def _parquet_safe_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce mixed-type object columns so pyarrow can serialize them.

    PosPal exports sometimes carry columns like ``充值环比增长率`` that mix
    numbers with ``'-'`` placeholders, which pyarrow rejects when it infers a
    numeric type. Strategy: if every non-null value is numeric-parseable the
    column is converted to numeric; otherwise it becomes a string column
    (preserving ``'-'`` etc.). Used columns are unaffected.
    """
    if df.empty or df.shape[1] == 0:
        return df
    df = df.copy()
    for col in df.columns:
        series = df[col]
        if series.dtype != object:
            continue
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() == series.notna().sum():
            df[col] = numeric
        else:
            df[col] = series.astype("string")
    return df


def _save_disk_cache(
    year: int,
    month: int,
    cached_at: float,
    live: LivePospalData,
    *,
    archived: bool = False,
) -> bool:
    """Persist a month bundle as parquet frames + meta.json.

    Returns ``True`` on success so callers can decide whether a legacy pickle
    is safe to delete (migration must not destroy the only disk copy).
    """
    live = sanitize_live_data(live)
    path = _disk_cache_path(year, month)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    shutil.rmtree(temp_path, ignore_errors=True)
    temp_path.mkdir(parents=True, exist_ok=True)
    try:
        meta = {
            "version": CACHE_FORMAT_VERSION,
            "cached_at": cached_at,
            "archived": bool(archived),
        }
        with (temp_path / "meta.json").open("w", encoding="utf-8") as handle:
            json.dump(meta, handle, ensure_ascii=False)
        for field in _LIVE_FIELDS:
            frame = getattr(live, field, None)
            if frame is None:
                frame = pd.DataFrame()
            _parquet_safe_frame(frame).to_parquet(
                temp_path / f"{field}.parquet", index=False
            )
        if path.exists():
            shutil.rmtree(path)
        os.replace(temp_path, path)
        return True
    except Exception:
        logger.warning("银豹月报持久缓存写入失败: %s", path, exc_info=True)
        shutil.rmtree(temp_path, ignore_errors=True)
        return False


def archive_month(year: int, month: int) -> bool:
    """Pin a month so it never expires (long-term archive).

    Fetches the month first if no usable cache exists, then marks the disk
    cache archived. Archived months skip the TTL on normal reads; a later
    ``force_refresh`` (still respecting the 6h quota floor) can refresh them.
    """
    key = (year, month)
    with _DOWNLOAD_LOCK:
        now = time.time()
        cached = _MONTHLY_CACHE.get(key)
        disk_cached = _load_disk_cache(year, month)
        if disk_cached and (cached is None or disk_cached[0] > cached[0]):
            cached = disk_cached
            _MONTHLY_CACHE[key] = disk_cached
        if cached is None:
            live = sanitize_live_data(_download_month(year, month))
            cached_at = now
        else:
            cached_at, live, _archived = cached
        entry = (cached_at, live, True)
        _MONTHLY_CACHE[key] = entry
        _save_disk_cache(year, month, cached_at, live, archived=True)
        return True


def invalidate_month_cache(year: int | None = None, month: int | None = None) -> int:
    """Drop cached monthly raw data.

    - invalidate_month_cache() — clear all in-process month entries.
    - invalidate_month_cache(2026, 6) — clear a single month.

    The persistent cache intentionally remains intact so a process restart or
    repeated refresh cannot bypass the free-quota protection interval.

    Returns the number of cache entries removed.
    """
    if year is None and month is None:
        n = len(_MONTHLY_CACHE)
        _MONTHLY_CACHE.clear()
        return n
    key = (year, month)
    if key in _MONTHLY_CACHE:
        del _MONTHLY_CACHE[key]
        return 1
    return 0


def monthly_cache_size() -> int:
    """Number of months currently held in the in-memory cache (for diagnostics)."""
    return len(_MONTHLY_CACHE)


def load_report_directory(report_dir: Path) -> LivePospalData:
    sales = _load_sales(report_dir / "商品销售流水.xlsx")
    loss = _load_loss(report_dir / "商品报损记录.xls")
    cards = _load_cards(report_dir / "储值卡数据统计.xls")
    cards_detail = _load_cards_detail(report_dir / "充值明细.xls")
    sales_detail = _load_sales_detail(report_dir / "销售流水单据.xlsx")
    payments = _load_payments(report_dir / "门店支付汇总.xlsx")
    return LivePospalData(
        sales=sales,
        loss=loss,
        cards=cards,
        cards_detail=cards_detail,
        sales_detail=sales_detail,
        payments=payments,
    )


def _load_payments(path: Path) -> pd.DataFrame:
    df = _read_excel(path)
    if df.empty:
        return df
    df["日期"] = pd.to_datetime(df.get("日期"), errors="coerce")
    for col in ["金额", "支付笔数", "交易单数", "营业实收"]:
        df[col] = _number_series(df, col)
    df["银豹支付方式"] = _text_series(df, "支付方式")
    df["支付方式"] = df["银豹支付方式"].map(normalize_payment_category)
    return df[df["日期"].notna()].copy()


def _load_sales(path: Path) -> pd.DataFrame:
    df = _read_excel(path)
    if df.empty:
        return df

    df = _drop_total_rows(df, "流水号")
    df["销售时间"] = pd.to_datetime(df.get("销售时间"), errors="coerce")
    for col in ["销售数量", "商品总价", "实收金额", "商品原价", "成本", "利润"]:
        df[col] = _number_series(df, col)

    df["日期"] = df["销售时间"].dt.date
    df["小时"] = df["销售时间"].dt.hour
    df["收入分类"] = df.apply(lambda row: classify_income(row.to_dict()), axis=1)
    df["来源"] = df.apply(_detect_sales_source, axis=1)
    return df[df["销售时间"].notna()].copy()


def _load_sales_detail(path: Path) -> pd.DataFrame:
    df = _read_excel(path)
    if df.empty:
        return df

    df = _drop_total_rows(df, "流水号")
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    for col in ["商品数量", "商品原价", "实收金额", "折让金额", "利润"]:
        if col in df.columns:
            df[col] = _number_series(df, col)
    if "备注" in df.columns:
        df["来源"] = df.apply(_detect_sales_source, axis=1)
    return df


def _load_loss(path: Path) -> pd.DataFrame:
    df = _read_excel(path)
    if df.empty:
        return df

    df = _drop_total_rows(df, "序号")
    if df.empty:
        return df

    df = df.rename(columns={"数量": "报废数量"})
    df["审核时间"] = pd.to_datetime(df.get("审核时间"), errors="coerce")
    df["调整日期"] = df["审核时间"].dt.date
    for col in ["报损金额", "金额", "报废数量"]:
        df[col] = _number_series(df, col)
    for col in ["备注", "报损原因", "商品分类", "商品名称"]:
        df[col] = _text_series(df, col)
    return df[df["审核时间"].notna()].copy()


def _load_cards(path: Path) -> pd.DataFrame:
    df = _read_excel(path)
    if df.empty:
        return df

    df["日期"] = pd.to_datetime(df.get("日期"), errors="coerce")
    for col in ["充值总金额", "储值卡消费总金额", "本金消费金额", "赠送消费金额"]:
        df[col] = _number_series(df, col)
    return df[df["日期"].notna()].copy()


def _load_cards_detail(path: Path) -> pd.DataFrame:
    df = _read_excel(path)
    if df.empty:
        return df

    df = _drop_total_rows(df, "充值门店")
    if "充值时间" in df.columns:
        df["充值时间"] = pd.to_datetime(df["充值时间"], errors="coerce")
        df["日期"] = df["充值时间"].dt.date
    for col in ["当前剩余金额", "充值金额", "赠送金额"]:
        if col in df.columns:
            df[col] = _number_series(df, col)
    if "支付方式" in df.columns:
        df["支付分类"] = df["支付方式"].map(normalize_payment_category)
    return df


def _read_excel(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_excel(path)


def _drop_total_rows(df: pd.DataFrame, marker_col: str) -> pd.DataFrame:
    if marker_col not in df.columns:
        return df.dropna(how="all").copy()
    marker = df[marker_col].astype(str)
    return df[~marker.str.contains("总计", na=False)].dropna(how="all").copy()


def _number_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([0] * len(df), index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def _text_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([""] * len(df), index=df.index)
    return df[col].fillna("").astype(str)


def _detect_sales_source(row: pd.Series) -> str:
    text = " ".join(str(v or "") for v in row.to_dict().values())
    rules: Dict[str, str] = {
        "美团": "美团",
        "MEITUAN": "美团",
        "饿了么": "饿了么",
        "ELEME": "饿了么",
        "抖音": "抖音",
        "DOUYIN": "抖音",
        "外卖": "外卖",
        "小程序": "小程序",
        "自营": "自营",
    }
    upper_text = text.upper()
    for keyword, source in rules.items():
        if keyword.upper() in upper_text:
            return source
    return "门店"
