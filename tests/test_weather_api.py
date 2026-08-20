from datetime import date, timedelta

from modules import weather_api


def _payload(start_date: date, end_date: date, code: int = 0) -> dict:
    days = (end_date - start_date).days + 1
    dates = [(start_date + timedelta(days=index)).isoformat() for index in range(days)]
    return {
        "daily": {
            "time": dates,
            "weather_code": [code] * days,
            "temperature_2m_max": [31.5] * days,
            "temperature_2m_min": [24.0] * days,
            "temperature_2m_mean": [27.8] * days,
            "precipitation_sum": [12.5] * days,
            "rain_sum": [12.5] * days,
            "precipitation_hours": [4.0] * days,
            "sunshine_duration": [18_000] * days,
            "wind_speed_10m_max": [16.2] * days,
        }
    }


def test_parse_daily_weather_normalizes_open_meteo_fields():
    frame = weather_api._parse_daily_response(
        _payload(date(2026, 6, 1), date(2026, 6, 1), code=63),
        data_type="历史再分析",
    )

    assert len(frame) == 1
    assert frame.loc[0, "日期"] == date(2026, 6, 1)
    assert frame.loc[0, "天气"] == "中雨"
    assert frame.loc[0, "天气类型"] == "中雨"
    assert frame.loc[0, "最高温"] == 31.5
    assert frame.loc[0, "降水量"] == 12.5
    assert frame.loc[0, "日照时长"] == 5.0
    assert bool(frame.loc[0, "是否降雨"]) is True
    assert frame.loc[0, "数据类型"] == "历史再分析"


def test_fetch_splits_archive_and_recent_dates_without_api_key(monkeypatch):
    today = date(2026, 8, 8)
    calls = []

    def fake_request(url: str, start_date: date, end_date: date) -> dict:
        calls.append((url, start_date, end_date))
        return _payload(start_date, end_date)

    monkeypatch.setattr(weather_api, "_china_today", lambda: today)
    monkeypatch.setattr(weather_api, "_request_daily_weather", fake_request)
    weather_api.clear_weather_cache()

    result = weather_api.fetch_store_daily_weather(
        date(2026, 8, 1), today, force_refresh=True
    )

    assert result.status == "available"
    assert len(result.data) == 8
    assert calls == [
        (weather_api.ARCHIVE_URL, date(2026, 8, 1), date(2026, 8, 3)),
        (weather_api.FORECAST_URL, date(2026, 8, 4), date(2026, 8, 8)),
    ]
    assert all("apikey" not in url.lower() for url, _, _ in calls)


def test_weather_description_uses_daily_precipitation_intensity():
    assert weather_api.describe_weather(0) == ("晴", "晴朗", "☀")
    assert weather_api.describe_weather(61, 8)[0] == "小雨"
    assert weather_api.describe_weather(61, 30)[0] == "大雨"
    assert weather_api.describe_weather(95, 30) == ("雷雨", "雷雨", "⛈")
