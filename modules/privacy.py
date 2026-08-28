"""Privacy-by-design transformations for the public portfolio dataset.

The dashboard only needs identifier equality for aggregation (for example,
counting orders), not the original POS identifiers. This module replaces
member, staff, store, transaction, and payment identifiers with stable,
synthetic labels while leaving business measures and product names intact.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd


_IDENTIFIER_PREFIXES = {
    "流水号": "TXN",
    "支付平台流水号": "PAY",
    "会员卡号": "CARD",
    "会员手机号": "PHONE",
    "充值会员": "MEMBER",
    "会员姓名": "MEMBER",
    "会员": "MEMBER",
    "收银员": "STAFF",
    "导购员": "STAFF",
    "报损人": "STAFF",
    "审核人": "STAFF",
    "销售门店": "STORE",
    "充值门店": "STORE",
    "开卡门店": "STORE",
    "门店编号": "STORE",
}

_SAFE_VALUES = {"", "-", "—", "nan", "nat", "none", "null", "未分类", "无"}


def _is_safe_label(value: str) -> bool:
    return any(
        value.startswith(f"{prefix}-")
        for prefix in set(_IDENTIFIER_PREFIXES.values())
    )


def _anonymize_series(
    series: pd.Series, prefix: str, mapping: Dict[str, str]
) -> pd.Series:
    next_id = len(mapping) + 1

    def replace(value: Any) -> Any:
        nonlocal next_id
        if pd.isna(value):
            return value
        text = str(value).strip()
        if text.lower() in _SAFE_VALUES or _is_safe_label(text):
            return value
        if text not in mapping:
            mapping[text] = f"{prefix}-{next_id:04d}"
            next_id += 1
        return mapping[text]

    return series.map(replace)


def sanitize_frame(
    frame: pd.DataFrame | None, mappings: Dict[str, Dict[str, str]]
) -> pd.DataFrame:
    """Return a copy with public-safe synthetic identifiers."""
    if frame is None or frame.empty:
        return frame.copy() if frame is not None else pd.DataFrame()
    result = frame.copy(deep=True)
    for column, prefix in _IDENTIFIER_PREFIXES.items():
        if column in result.columns:
            result[column] = _anonymize_series(
                result[column], prefix, mappings.setdefault(prefix, {})
            )
    return result


def sanitize_live_data(live: Any) -> Any:
    """Sanitize every frame in a ``LivePospalData``-shaped object."""
    mappings: Dict[str, Dict[str, str]] = {}
    fields = ("sales", "loss", "cards", "cards_detail", "sales_detail", "payments")
    values = {
        field: sanitize_frame(getattr(live, field, None), mappings)
        for field in fields
    }
    if hasattr(live, "source"):
        values["source"] = getattr(live, "source", "unknown")
    return type(live)(**values)
