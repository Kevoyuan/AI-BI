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
