"""Persistent free-quota guard for PosPal OpenAPI calls.

PosPal OpenAPI V3 grants 10,000 Token on the first console login.  The guard
keeps a conservative local ledger and refuses a request before the configured
budget can be exceeded.  It deliberately charges attempted requests: doing so
is safer than assuming that a failed or timed-out request was not billed.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator

try:  # Unix/macOS cross-process lock; tests and production both run on macOS.
    import fcntl
except ImportError:  # pragma: no cover - Windows compatibility fallback
    fcntl = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FREE_TOKEN_GRANT = 10_000
DEFAULT_TOKEN_BUDGET = 9_000
DEFAULT_UNKNOWN_QUERY_COST = 1_000


class PospalQuotaExceeded(RuntimeError):
    """Raised before an OpenAPI call would exceed the local free budget."""


class PospalQuotaLedgerError(RuntimeError):
    """Raised when the ledger cannot be trusted; fail closed to protect quota."""


@dataclass(frozen=True)
class PospalQuotaPolicy:
    free_token_grant: int = DEFAULT_FREE_TOKEN_GRANT
    token_budget: int = DEFAULT_TOKEN_BUDGET
    unknown_query_cost: int = DEFAULT_UNKNOWN_QUERY_COST
    ledger_path: Path = PROJECT_ROOT / ".cache" / "pospal-openapi-quota.json"
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "PospalQuotaPolicy":
        grant = _positive_int("POSPAL_FREE_TOKEN_GRANT", DEFAULT_FREE_TOKEN_GRANT)
        requested_budget = _positive_int("POSPAL_OPENAPI_TOKEN_BUDGET", DEFAULT_TOKEN_BUDGET)
        budget = min(requested_budget, grant)
        return cls(
            free_token_grant=grant,
            token_budget=budget,
            unknown_query_cost=_positive_int(
                "POSPAL_UNKNOWN_QUERY_TOKEN_COST", DEFAULT_UNKNOWN_QUERY_COST
            ),
            ledger_path=Path(
                os.environ.get(
                    "POSPAL_QUOTA_LEDGER_PATH",
                    str(PROJECT_ROOT / ".cache" / "pospal-openapi-quota.json"),
                )
            ).expanduser(),
            enabled=os.environ.get("POSPAL_ENFORCE_FREE_QUOTA", "1").strip().lower()
            not in {"0", "false", "no", "off"},
        )


_THREAD_LOCK = threading.RLock()


class PospalQuotaGuard:
    def __init__(self, policy: PospalQuotaPolicy | None = None):
        self.policy = policy or PospalQuotaPolicy.from_env()

    def reserve(self, endpoint: str, payload: Dict[str, Any], token_cost: int | None = None) -> int:
        """Reserve budget for one attempted request and return its estimated cost."""
        if not self.policy.enabled:
            return 0
        cost = token_cost if token_cost is not None else estimate_token_cost(
            endpoint, payload, unknown_cost=self.policy.unknown_query_cost
        )
        if cost <= 0:
            raise ValueError("token_cost must be positive")

        with _THREAD_LOCK, self._locked_ledger() as ledger:
            used = int(ledger.get("usedTokens", 0))
            if used + cost > self.policy.token_budget:
                remaining = max(self.policy.token_budget - used, 0)
                raise PospalQuotaExceeded(
                    "银豹免费额度保护已阻止本次查询："
                    f"预计需要 {cost} Token，本地安全余额仅 {remaining} Token；"
                    f"安全上限为 {self.policy.token_budget}/{self.policy.free_token_grant} Token。"
                )

            ledger["version"] = 1
            ledger["freeTokenGrant"] = self.policy.free_token_grant
            ledger["tokenBudget"] = self.policy.token_budget
            ledger["usedTokens"] = used + cost
            ledger["updatedAt"] = datetime.now(timezone.utc).isoformat()
            entries = list(ledger.get("recentRequests") or [])
            entries.append(
                {
                    "at": ledger["updatedAt"],
                    "endpoint": endpoint,
                    "estimatedTokens": cost,
                }
            )
            ledger["recentRequests"] = entries[-100:]
            self._write_ledger(ledger)
        return cost

    def status(self) -> Dict[str, int | bool]:
        if not self.policy.enabled:
            return {"enabled": False, "usedTokens": 0, "remainingTokens": 0}
        with _THREAD_LOCK, self._locked_ledger() as ledger:
            used = int(ledger.get("usedTokens", 0))
        return {
            "enabled": True,
            "freeTokenGrant": self.policy.free_token_grant,
            "tokenBudget": self.policy.token_budget,
            "usedTokens": used,
            "remainingTokens": max(self.policy.token_budget - used, 0),
        }

    @contextmanager
    def _locked_ledger(self) -> Iterator[Dict[str, Any]]:
        path = self.policy.ledger_path
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield self._read_ledger()
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_ledger(self) -> Dict[str, Any]:
        path = self.policy.ledger_path
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PospalQuotaLedgerError(
                f"银豹额度账本无法读取，已停止调用以避免超额：{path}"
            ) from exc
        if not isinstance(data, dict) or int(data.get("usedTokens", 0)) < 0:
            raise PospalQuotaLedgerError(f"银豹额度账本格式无效：{path}")
        return data

    def _write_ledger(self, ledger: Dict[str, Any]) -> None:
        path = self.policy.ledger_path
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temp_path, path)


def estimate_token_cost(
    endpoint: str, payload: Dict[str, Any], *, unknown_cost: int = DEFAULT_UNKNOWN_QUERY_COST
) -> int:
    """Estimate current V3 Token cost from endpoint and request switches.

    Unknown routes fail conservatively at 1,000 Token by default. Callers may
    pass an explicit ``token_cost`` to ``PospalOpenApiClient.post`` when adding
    a newly documented endpoint.
    """
    route = endpoint.lower().split("?", 1)[0].rstrip("/")
    need_count = sum(
        1 for key, value in payload.items() if key.lower().startswith("need") and value is True
    )

    if route.endswith("/product/increment-page"):
        return 100 + 20 * need_count
    if route.endswith("/customer/increment-page"):
        return 100 + 20 * need_count
    if route.endswith("/ticket/increment-page"):
        precise = any(payload.get(key) not in (None, "") for key in ("uid", "customerUid", "sn", "webOrderNo"))
        return (100 + 20 * need_count) if precise else (800 + 50 * need_count)
    if route.endswith("ticketopenapi/queryticketpages"):
        # Legacy client route.  Reserve the V3 range-query equivalent so a
        # future endpoint migration cannot silently bypass the free guard.
        return 800
    if route.endswith("/product/stock-page"):
        return 500
    if "discard" in route and (route.endswith("-page") or route.endswith("/page")):
        return 500
    if any(part in route for part in ("recharge", "prepaid-card")) and (
        payload.get("datetimeBegin") or payload.get("datetimeEnd")
    ):
        return 500
    if any(part in route for part in ("product-order", "online-order")) and route.endswith(
        ("-page", "/page")
    ):
        precise = any(payload.get(key) not in (None, "") for key in ("uid", "sn", "orderNo"))
        return (100 + 20 * need_count) if precise else (800 + 50 * need_count)
    if any(part in route for part in ("stock-flow", "flow-order")) and route.endswith(
        ("-page", "/page")
    ):
        return 500

    known_fixed_100_suffixes = (
        "/category/list",
        "/category-page",
        "/tag-page",
        "/unit-page",
        "/brand-page",
        "/supplier-page",
        "/attribute-page",
        "/store/increment-page",
        "/cashier/increment-page",
    )
    if route.endswith(known_fixed_100_suffixes):
        return 100
    return unknown_cost


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default
