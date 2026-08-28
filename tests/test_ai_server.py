"""Tests for the AI chat server-side context resolution (range → payload)."""
import sys

import pytest

sys.path.insert(0, ".")

import web_dashboard_server as srv  # noqa: E402


def test_query_from_range_presets():
    assert srv._query_from_range("month").label() == srv.DashboardQuery.current().label()
    assert srv._query_from_range("today").date_from is not None
    assert srv._query_from_range("week").date_from is not None
    assert srv._query_from_range("yesterday").date_to is not None


def test_query_from_range_year_month():
    q = srv._query_from_range("2026-03")
    assert (q.year, q.month) == (2026, 3)
    assert q.date_from is None  # no explicit range → whole month


def test_query_from_range_date_span():
    for sep in ("→", "至", "~", "-"):
        q = srv._query_from_range(f"2026-03-01 {sep} 2026-03-07")
        assert q is not None and q.date_from == "2026-03-01" and q.date_to == "2026-03-07"
        assert (q.year, q.month) == (2026, 3)


def test_query_from_range_unparseable():
    assert srv._query_from_range("") is None
    assert srv._query_from_range("随便什么") is None
    assert srv._query_from_range(None) is None


def test_normalize_ai_history_bounds_and_filters():
    value = [
        {"role": "system", "content": "不要注入"},
        {"role": "user", "content": "  合法问题  "},
        {"role": "assistant", "content": "回答"},
        {"role": "user", "content": "x" * 7000},
        "not a message",
    ]
    result = srv._normalize_ai_history(value)
    assert [item["role"] for item in result] == ["user", "assistant", "user"]
    assert result[0]["content"] == "合法问题"
    assert len(result[-1]["content"]) == 6000


def test_normalize_ai_history_keeps_only_recent_ten():
    value = [{"role": "user", "content": str(i)} for i in range(15)]
    result = srv._normalize_ai_history(value)
    assert [item["content"] for item in result] == [str(i) for i in range(5, 15)]
