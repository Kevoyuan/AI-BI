import json

import pytest

from modules.pospal_quota import (
    PospalQuotaExceeded,
    PospalQuotaGuard,
    PospalQuotaPolicy,
    estimate_token_cost,
)


def test_estimates_current_v3_query_costs():
    assert estimate_token_cost("/openapi/v3/product/increment-page", {}) == 100
    assert estimate_token_cost(
        "/openapi/v3/customer/increment-page",
        {"needCustomerExt": True, "needCustomerTag": False},
    ) == 120
    assert estimate_token_cost(
        "/openapi/v3/ticket/increment-page",
        {"datetimeBegin": "2026-08-01 00:00:00", "needTicketItems": True},
    ) == 850
    assert estimate_token_cost(
        "/openapi/v3/ticket/increment-page",
        {"sn": "T1", "needTicketItems": True},
    ) == 120
    assert estimate_token_cost("/openapi/v3/product/stock-page", {}) == 500
    assert estimate_token_cost("/openapi/v3/future/unknown-page", {}) == 1000


def test_guard_persists_attempts_and_blocks_before_budget(tmp_path):
    ledger = tmp_path / "quota.json"
    guard = PospalQuotaGuard(
        PospalQuotaPolicy(
            free_token_grant=1000,
            token_budget=899,
            unknown_query_cost=1000,
            ledger_path=ledger,
        )
    )

    assert guard.reserve("/openapi/v3/ticket/increment-page", {}) == 800
    with pytest.raises(PospalQuotaExceeded):
        guard.reserve("/openapi/v3/product/increment-page", {})

    saved = json.loads(ledger.read_text(encoding="utf-8"))
    assert saved["usedTokens"] == 800
    assert guard.status()["remainingTokens"] == 99
