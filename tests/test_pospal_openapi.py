import hashlib
import re

from modules.pospal_openapi import (
    PospalOpenApiClient,
    PospalOpenApiConfig,
    classify_income,
    normalize_payment_category,
    normalize_tickets,
)
from modules.pospal_webapi import parse_html_table_rows


def test_v1_signature_uses_app_key_and_body():
    config = PospalOpenApiConfig(app_id="app", app_key="secret")
    client = PospalOpenApiClient(config)
    body = '{"appId":"app"}'
    headers = client._headers(body)
    assert headers["data-signature"] == hashlib.md5(("secret" + body).encode()).hexdigest()


def test_v3_signature_uses_current_official_headers(monkeypatch):
    monkeypatch.setattr("modules.pospal_openapi.time.time", lambda: 1_700_000_000)
    monkeypatch.setattr(
        "modules.pospal_openapi.uuid.uuid4",
        lambda: "550e8400-e29b-41d4-a716-446655440000",
    )
    config = PospalOpenApiConfig(
        app_id="app", app_key="secret", signature_version="v3"
    )
    client = PospalOpenApiClient(config)
    headers = client._headers("{}")
    raw = "app|550e8400-e29b-41d4-a716-446655440000|1700000000|secret"

    assert headers["X-App-Id"] == "app"
    assert headers["X-Timestamp"] == "1700000000"
    assert headers["X-Request-Id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert headers["X-Sign"] == hashlib.md5(raw.encode()).hexdigest().upper()
    assert re.fullmatch(r"[0-9A-F]{32}", headers["X-Sign"])


def test_classify_income_from_any_layer():
    assert classify_income({"商品名称": "草莓生日蛋糕", "商品分类": "西点"}) == "蛋糕"
    assert classify_income({"商品名称": "无码商品"}, {"备注": "美团外卖订单"}) == "美团"
    assert classify_income({"商品分类": "现烤", "商品名称": "红豆包"}) == "现烤"


def test_normalize_payment_category():
    assert normalize_payment_category("美团付款") == "美团"
    assert normalize_payment_category("银豹付支付") == "微信/支付宝"
    assert normalize_payment_category("储值卡支付") == "储值卡"


def test_normalize_tickets_flattens_rows():
    tickets = [{
        "ticketSn": "T1",
        "ticketTime": "2026-06-07 10:00:00",
        "actualAmount": 68,
        "remark": "美团",
        "items": [{"productName": "芒果蛋糕", "quantity": 1, "actualAmount": 68}],
        "payments": [{"payMethod": "美团付款", "amount": 68}],
    }]
    ticket_df, item_df, payment_df = normalize_tickets(tickets)
    assert ticket_df.iloc[0]["流水号"] == "T1"
    assert item_df.iloc[0]["收入分类"] == "蛋糕"
    assert item_df.iloc[0]["来源"] == "美团"
    assert payment_df.iloc[0]["收入分类"] == "美团"


def test_parse_card_summary_html_table_rows():
    html = """
    <thead><tr><th>日期</th><th>充值总金额</th></tr></thead>
    <tbody><tr><td>2026-06-01</td><td>1,234.50</td></tr></tbody>
    """
    rows = parse_html_table_rows(html)
    assert rows == [["日期", "充值总金额"], ["2026-06-01", 1234.5]]
