"""Free daily weather data for Humen, Dongguan via Open-Meteo.

The client intentionally has no API-key dependency.  It uses the Archive API
for older dates and the Forecast API for the most recent few days, then
normalizes both response shapes into one DataFrame for dashboard analytics.
Failures are returned as an unavailable result so weather never takes down the
primary PosPal dashboard.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import requests


HUMEN_LATITUDE = float(os.environ.get("STORE_WEATHER_LATITUDE", "22.81899"))
HUMEN_LONGITUDE = float(os.environ.get("STORE_WEATHER_LONGITUDE", "113.67306"))
HUMEN_LOCATION = os.environ.get("STORE_WEATHER_LOCATION", "示范城市 · 示范区")
WEATHER_TIMEZONE = "Asia/Shanghai"
ARCHIVE_URL = os.environ.get(
    "OPEN_METEO_ARCHIVE_URL", "https://archive-api.open-meteo.com/v1/archive"
)
FORECAST_URL = os.environ.get(
    "OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast"
)
DAILY_FIELDS = (
    "weather_code,temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
    "precipitation_sum,rain_sum,precipitation_hours,sunshine_duration,"
    "wind_speed_10m_max"
)
WEATHER_CACHE_TTL_SECONDS = 1800
HISTORICAL_CACHE_TTL_SECONDS = 21600
# ERA5-style archive data can lag by about five days.  Use the forecast API's
# recent-history window only for those latest days, and the archive everywhere
# else so long-range impact analysis stays consistent.
_RECENT_HISTORY_DAYS = 4


@dataclass
class WeatherApiResult:
    data: pd.DataFrame
    status: str
    message: str
    provider: str = "Open-Meteo"
    location: str = HUMEN_LOCATION
    latitude: float = HUMEN_LATITUDE
    longitude: float = HUMEN_LONGITUDE
    fetched_at: str | None = None


_CACHE: Dict[Tuple[str, str, float, float], Tuple[float, WeatherApiResult]] = {}
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "bllz-analytics/1.0 weather-impact"})


def _china_today() -> date:
    return datetime.now(ZoneInfo(WEATHER_TIMEZONE)).date()


def _clone_result(result: WeatherApiResult) -> WeatherApiResult:
    return WeatherApiResult(
        data=result.data.copy(deep=True),
        status=result.status,
        message=result.message,
        provider=result.provider,
        location=result.location,
        latitude=result.latitude,
        longitude=result.longitude,
        fetched_at=result.fetched_at,
    )


def clear_weather_cache() -> None:
    _CACHE.clear()


def fetch_store_daily_weather(
    start_date: date,
    end_date: date,
    *,
    force_refresh: bool = False,
) -> WeatherApiResult:
    """Fetch normalized daily weather for Humen without requiring an API key."""
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    if start_date > end_date:
        return WeatherApiResult(
            data=pd.DataFrame(),
            status="unavailable",
            message="天气查询开始日期晚于结束日期",
        )

    key = (
        start_date.isoformat(),
        end_date.isoformat(),
        HUMEN_LATITUDE,
        HUMEN_LONGITUDE,
    )
    now = time.monotonic()
    today = _china_today()
    ttl = (
        HISTORICAL_CACHE_TTL_SECONDS
        if end_date < today
        else WEATHER_CACHE_TTL_SECONDS
    )
    cached = _CACHE.get(key)
    if not force_refresh and cached and now - cached[0] < ttl:
        return _clone_result(cached[1])

    recent_start = today - timedelta(days=_RECENT_HISTORY_DAYS)
    forecast_end = today + timedelta(days=15)
    segments: List[Tuple[str, date, date, str]] = []
    if start_date < recent_start:
        segments.append(
            (
                ARCHIVE_URL,
                start_date,
                min(end_date, recent_start - timedelta(days=1)),
                "历史再分析",
            )
        )
    if end_date >= recent_start and start_date <= forecast_end:
        segments.append(
            (
                FORECAST_URL,
                max(start_date, recent_start),
                min(end_date, forecast_end),
                "近期/预报",
            )
        )

    frames: List[pd.DataFrame] = []
    errors: List[str] = []
    for url, segment_start, segment_end, data_type in segments:
        if segment_start > segment_end:
            continue
        try:
            payload = _request_daily_weather(url, segment_start, segment_end)
            frame = _parse_daily_response(payload, data_type=data_type)
            if not frame.empty:
                frames.append(frame)
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append(str(exc))

    if frames:
        data = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["日期"], keep="last")
            .sort_values("日期")
            .reset_index(drop=True)
        )
        status = "partial" if errors else "available"
        message = (
            f"已获取虎门 {len(data)} 天天气；部分日期获取失败"
            if errors
            else f"已获取虎门 {len(data)} 天天气"
        )
    else:
        data = pd.DataFrame()
        status = "unavailable"
        message = errors[-1] if errors else "所选日期暂无可用天气数据"

    result = WeatherApiResult(
        data=data,
        status=status,
        message=message,
        fetched_at=datetime.now(ZoneInfo(WEATHER_TIMEZONE)).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    )
    _CACHE[key] = (now, result)
    return _clone_result(result)


def _request_daily_weather(url: str, start_date: date, end_date: date) -> Dict[str, Any]:
    params = {
        "latitude": HUMEN_LATITUDE,
        "longitude": HUMEN_LONGITUDE,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": DAILY_FIELDS,
        "timezone": WEATHER_TIMEZONE,
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = _SESSION.get(url, params=params, timeout=(4, 12))
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(
                    f"Open-Meteo 暂时不可用（HTTP {response.status_code}）",
                    response=response,
                )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise ValueError(str(payload.get("reason") or "天气接口返回错误"))
            return payload
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.25 * (2**attempt))
    raise requests.RequestException(f"虎门天气获取失败：{last_error}")


def _parse_daily_response(payload: Dict[str, Any], *, data_type: str) -> pd.DataFrame:
    daily = payload.get("daily")
    if not isinstance(daily, dict) or not isinstance(daily.get("time"), list):
        raise ValueError("天气接口缺少 daily.time")

    rows: List[Dict[str, Any]] = []
    for index, day in enumerate(daily["time"]):
        code = int(_daily_value(daily, "weather_code", index, 0) or 0)
        precipitation = float(
            _daily_value(daily, "precipitation_sum", index, 0) or 0
        )
        description, category, icon = describe_weather(code, precipitation)
        rows.append(
            {
                "日期": pd.to_datetime(day, errors="raise").date(),
                "天气代码": code,
                "天气": description,
                "天气类型": category,
                "天气图标": icon,
                "最高温": _number_or_none(_daily_value(daily, "temperature_2m_max", index)),
                "最低温": _number_or_none(_daily_value(daily, "temperature_2m_min", index)),
                "平均温度": _number_or_none(_daily_value(daily, "temperature_2m_mean", index)),
                "降水量": precipitation,
                "降雨量": float(_daily_value(daily, "rain_sum", index, 0) or 0),
                "降水时长": float(_daily_value(daily, "precipitation_hours", index, 0) or 0),
                "日照时长": round(float(_daily_value(daily, "sunshine_duration", index, 0) or 0) / 3600, 1),
                "最大风速": _number_or_none(_daily_value(daily, "wind_speed_10m_max", index)),
                "是否降雨": precipitation >= 0.1,
                "数据类型": data_type,
            }
        )
    return pd.DataFrame(rows)


def _daily_value(
    daily: Dict[str, Any], key: str, index: int, default: Any = None
) -> Any:
    values = daily.get(key)
    if not isinstance(values, list) or index >= len(values):
        return default
    value = values[index]
    return default if value is None else value


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def describe_weather(code: int, precipitation: float = 0) -> Tuple[str, str, str]:
    """Map WMO weather codes and daily precipitation to concise Chinese labels."""
    if code == 0:
        return "晴", "晴朗", "☀"
    if code == 1:
        return "大致晴朗", "晴朗", "🌤"
    if code == 2:
        return "多云", "多云", "⛅"
    if code == 3:
        return "阴", "阴天", "☁"
    if code in (45, 48):
        return "雾", "雾", "🌫"
    if code in (95, 96, 99):
        return "雷雨", "雷雨", "⛈"
    if code in (71, 73, 75, 77, 85, 86):
        return "降雪", "降雪", "❄"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        if precipitation >= 50:
            return "暴雨", "暴雨", "🌧"
        if precipitation >= 25:
            return "大雨", "大雨", "🌧"
        if precipitation >= 10:
            return "中雨", "中雨", "🌧"
        return "小雨", "小雨", "🌦"
    return "天气未知", "其他", "◌"

# Backwards-compatible alias
fetch_humen_daily_weather = fetch_store_daily_weather
