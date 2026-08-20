"""
银豹/PosPal OpenAPI client.

官方开放接口通常使用 appId/appKey 签名，不使用网页后台的
POSPAL_USER/POSPAL_PASSWORD。这里先封装订单查询和扁平化，方便后续替换
Selenium 下载流程。
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests

from modules.pospal_quota import PospalQuotaGuard


DEFAULT_API_BASE_URL = "https://openapi.pospal.cn/pospal-api2/openapi/v1"


@dataclass
class PospalOpenApiConfig:
    app_id: str
    app_key: str
    base_url: str = DEFAULT_API_BASE_URL
    signature_version: str = "v1"
    timeout: int = 30

    @classmethod
    def from_env(cls) -> "PospalOpenApiConfig":
        app_id = os.environ.get("POSPAL_APP_ID", "").strip()
        app_key = os.environ.get("POSPAL_APP_KEY", "").strip()
        if not app_id or not app_key:
            raise RuntimeError("请设置 POSPAL_APP_ID 和 POSPAL_APP_KEY")

        return cls(
            app_id=app_id,
            app_key=app_key,
            base_url=os.environ.get("POSPAL_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/"),
            signature_version=os.environ.get("POSPAL_SIGNATURE_VERSION", "v1"),
            timeout=int(os.environ.get("POSPAL_API_TIMEOUT", "30")),
        )


class PospalOpenApiClient:
    def __init__(
        self,
        config: PospalOpenApiConfig,
        quota_guard: PospalQuotaGuard | None = None,
    ):
        self.config = config
        self.session = requests.Session()
        self.quota_guard = quota_guard or PospalQuotaGuard()

    def _headers(self, body: str) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "bllz-analytics/1.0",
        }

        if self.config.signature_version == "v3":
            timestamp = str(int(time.time()))
            request_id = str(uuid.uuid4())
            signature_text = (
                f"{self.config.app_id}|{request_id}|{timestamp}|{self.config.app_key}"
            )
            headers.update({
                "X-App-Id": self.config.app_id,
                "X-Timestamp": timestamp,
                "X-Request-Id": request_id,
                "X-Sign": hashlib.md5(signature_text.encode("utf-8")).hexdigest().upper(),
            })
            return headers

        headers["data-signature"] = hashlib.md5(
            (self.config.app_key + body).encode("utf-8")
        ).hexdigest()
        return headers

    def post(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        *,
        token_cost: int | None = None,
    ) -> Dict[str, Any]:
        import json

        request_payload = (
            dict(payload)
            if self.config.signature_version == "v3"
            else {"appId": self.config.app_id, **payload}
        )
        body = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":"))
        url = f"{self.config.base_url}/{endpoint.lstrip('/')}"
        self.quota_guard.reserve(endpoint, request_payload, token_cost=token_cost)
        response = self.session.post(
            url,
            data=body.encode("utf-8"),
            headers=self._headers(body),
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        data = response.json()

        status = data.get("status") or data.get("success")
        if status not in (None, "success", True, 0, "0"):
            raise RuntimeError(f"银豹 OpenAPI 返回失败: {data}")
        return data

    def query_ticket_pages(
        self,
        start_time: datetime,
        end_time: datetime,
        page_no: int = 1,
        page_size: int = 100,
        **extra: Any,
    ) -> Dict[str, Any]:
        payload = {
            "startTime": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "endTime": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "pageNo": page_no,
            "pageSize": page_size,
            **extra,
        }
        return self.post("ticketOpenApi/queryTicketPages", payload)

    def iter_tickets(
        self,
        start_time: datetime,
        end_time: datetime,
        page_size: int = 100,
        **extra: Any,
    ) -> Iterable[Dict[str, Any]]:
        page_no = 1
        while True:
            data = self.query_ticket_pages(start_time, end_time, page_no, page_size, **extra)
            rows, total = _extract_rows_and_total(data)
            for row in rows:
                yield row

            if not rows or len(rows) < page_size or page_no * page_size >= total:
                break
            page_no += 1


def _extract_rows_and_total(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
    container = data.get("data") if isinstance(data.get("data"), dict) else data
    rows = (
        container.get("rows")
        or container.get("result")
        or container.get("tickets")
        or container.get("list")
        or []
    )
    total = container.get("total") or container.get("totalCount") or len(rows)
    return list(rows), int(total or 0)


def _first_present(row: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def normalize_tickets(tickets: Iterable[Dict[str, Any]]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """将 OpenAPI 订单结构拆成订单、商品明细、支付明细三张表。"""
    ticket_rows: List[Dict[str, Any]] = []
    item_rows: List[Dict[str, Any]] = []
    payment_rows: List[Dict[str, Any]] = []

    for ticket in tickets:
        sn = _first_present(ticket, ["sn", "ticketSn", "ticketNo", "流水号"])
        ticket_time = _first_present(ticket, ["datetime", "ticketTime", "salesTime", "日期"])
        received = _first_present(ticket, ["received", "receiveAmount", "actualAmount", "实收金额"], 0)
        ticket_rows.append({
            "流水号": sn,
            "日期": ticket_time,
            "类型": _first_present(ticket, ["ticketType", "type", "类型"]),
            "会员": _first_present(ticket, ["customerName", "memberName", "会员"]),
            "实收金额": received,
            "折让金额": _first_present(ticket, ["discount", "discountAmount", "折让金额"], 0),
            "备注": _first_present(ticket, ["remark", "备注"]),
            "单据标签": _first_present(ticket, ["tag", "tags", "单据标签"]),
            "来源": _detect_source(ticket),
        })

        for item in ticket.get("items") or ticket.get("ticketItems") or ticket.get("details") or []:
            item_rows.append({
                "流水号": sn,
                "销售时间": ticket_time,
                "商品名称": _first_present(item, ["name", "productName", "商品名称", "商品信息"]),
                "商品条码": _first_present(item, ["barcode", "productBarcode", "商品条码"]),
                "商品分类": _first_present(item, ["categoryName", "category", "商品分类"]),
                "销售数量": _first_present(item, ["quantity", "qty", "商品数量", "销售数量"], 0),
                "商品总价": _first_present(item, ["total", "amount", "商品总价"], 0),
                "实收金额": _first_present(item, ["received", "receiveAmount", "actualAmount", "实收金额"], 0),
                "收入分类": classify_income(item, ticket),
                "来源": _detect_source(ticket),
            })

        for payment in ticket.get("payments") or ticket.get("payDetails") or ticket.get("paymentDetails") or []:
            method = _first_present(payment, ["method", "payMethod", "paymentName", "支付方式"])
            payment_rows.append({
                "流水号": sn,
                "日期": ticket_time,
                "支付方式": method,
                "金额": _first_present(payment, ["amount", "payAmount", "金额"], 0),
                "收入分类": normalize_payment_category(method),
                "来源": _detect_source({**ticket, **payment}),
            })

    return pd.DataFrame(ticket_rows), pd.DataFrame(item_rows), pd.DataFrame(payment_rows)


def normalize_payment_category(method: Optional[str]) -> str:
    text = str(method or "")
    rules = [
        ("美团", "美团"),
        ("外卖", "外卖"),
        ("抖音", "抖音"),
        ("微信", "微信/支付宝"),
        ("支付宝", "微信/支付宝"),
        ("银豹付", "微信/支付宝"),
        ("现金", "现金"),
        ("储值", "储值卡"),
        ("会员卡", "储值卡"),
    ]
    for keyword, category in rules:
        if keyword in text:
            return category
    return text or "其他支付"


def classify_income(item: Dict[str, Any], ticket: Optional[Dict[str, Any]] = None) -> str:
    """按商品分类、商品名、订单来源等多层级自动归类收入。"""
    ticket = ticket or {}
    item_text = " ".join(
        str(v or "")
        for v in [
            item.get("categoryName"), item.get("category"), item.get("商品分类"),
            item.get("name"), item.get("productName"), item.get("商品名称"), item.get("商品信息"),
        ]
    )
    ticket_text = " ".join(
        str(v or "")
        for v in [
            ticket.get("remark"), ticket.get("备注"), ticket.get("tag"), ticket.get("tags"), ticket.get("单据标签"),
            ticket.get("source"), ticket.get("platform"), ticket.get("来源"),
        ]
    )

    rules = [
        ("美团", "美团"),
        ("外卖", "外卖"),
        ("蛋糕", "蛋糕"),
        ("生日蛋糕", "蛋糕"),
        ("分享蛋糕", "蛋糕"),
        ("现烤", "现烤"),
        ("西点", "西点"),
        ("饮品", "饮品"),
        ("饼干", "手工饼干"),
    ]
    for keyword, category in rules:
        if keyword in item_text:
            return category

    for keyword, category in rules:
        if keyword in ticket_text:
            return category
    return str(item.get("categoryName") or item.get("category") or item.get("商品分类") or "未分类")


def _detect_source(row: Dict[str, Any]) -> str:
    text = " ".join(str(v or "") for v in row.values())
    for keyword in ["美团", "饿了么", "外卖", "抖音", "小程序", "网店"]:
        if keyword in text:
            return keyword
    return "门店"
