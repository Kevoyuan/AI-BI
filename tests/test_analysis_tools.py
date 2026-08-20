"""Tests for the parameterized analysis tools (forecast + weather impact)."""
import sys
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, ".")

from modules import analysis_tools as at  # noqa: E402


def _synthetic_sales(days=60) -> pd.DataFrame:
    """Daily revenue with a mild upward trend + weekday rhythm."""
    today = date.today()
    rows = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        dow = d.weekday()
        base = 5000 + i * 40 + (1500 if dow >= 5 else 0)
        rows.append({"日期": d, "实收金额": float(base + i % 7 * 100)})
    return pd.DataFrame(rows)


def test_resolve_window_presets():
    today = date.today()
    s, e = at.resolve_window({"preset": "today"})
    assert (s, e) == (today, today)
    s, e = at.resolve_window({"preset": "week"})
    assert s.weekday() == 0 and e >= s
    s, e = at.resolve_window({"year": 2026, "month": 3})
    assert (s, e) == (date(2026, 3, 1), date(2026, 3, 31))
    s, e = at.resolve_window({"date_from": "2026-03-01", "date_to": "2026-03-07"})
    assert (s, e) == (date(2026, 3, 1), date(2026, 3, 7))
    # default + clamp to 90 days / today
    s, e = at.resolve_window(None, default_days=30)
    assert (e - s).days <= 90 and e <= today


def test_normalize_weather_labels():
    df = pd.DataFrame({"日期": [date(2026, 8, 1)], "天气": ["晴"]})
    out = at._normalize_weather(df)
    assert out["天气"].iloc[0] == "晴天"
    df2 = pd.DataFrame({"日期": [date(2026, 8, 1)], "天气": ["暴雨"]})
    assert at._normalize_weather(df2)["天气"].iloc[0] == "暴雨"


def test_run_forecast_tomorrow(monkeypatch):
    monkeypatch.setattr(at, "_fetch_sales_window", lambda s, e: _synthetic_sales())
    res = at.run_forecast({"preset": "month"}, horizon="tomorrow")
    assert res["analysis"] == "forecast" and res["horizon"] == "tomorrow"
    assert "预测明天销售额" in res["result"]
    assert res["result"]["预测明天销售额"] > 0
    assert "置信下限" in res["result"]


def test_run_forecast_next_week(monkeypatch):
    monkeypatch.setattr(at, "_fetch_sales_window", lambda s, e: _synthetic_sales(80))
    res = at.run_forecast(None, horizon="next_week")
    assert "预测下周销售额" in res["result"]
    assert "趋势方向" in res["result"]
    assert res["result"]["预测下周销售额"] > 0


def test_run_weather_impact(monkeypatch):
    sales = _synthetic_sales(30)
    weather = pd.DataFrame(
        {
            "日期": sorted(set(sales["日期"].tolist()))[:30],
            "天气": ["晴天"] * 20 + ["小雨"] * 10,
        }
    )
    monkeypatch.setattr(at, "_fetch_sales_window", lambda s, e: sales)
    monkeypatch.setattr(at, "_fetch_weather_window", lambda s, e: weather)

    res = at.run_weather_impact(None)
    assert res["analysis"] == "weather"
    assert res["影响系数"] is not None
    labels = {r["天气"] for r in res["影响系数"]}
    assert "晴天" in labels  # baseline present after normalization
    assert "预警" in res


def test_run_weather_impact_insufficient(monkeypatch):
    monkeypatch.setattr(at, "_fetch_sales_window", lambda s, e: pd.DataFrame())
    res = at.run_weather_impact(None)
    assert "error" in res
