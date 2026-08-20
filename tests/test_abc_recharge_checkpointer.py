"""Unit tests for Product ABC, Recharge Health, and LangGraph Checkpointer."""

import asyncio
import sys
import pandas as pd
import pytest

sys.path.insert(0, ".")

from skills.deep_analysis.scripts.product_abc import analyze_product_abc
from skills.profit_cost.scripts.recharge_health import analyze_recharge_health
from modules.analysis_tools import run_product_abc, run_recharge_health
from modules import ai_assistant as ai


def test_product_abc_analysis():
    # Construct products with different revenues
    data = [
        {"商品名称": "招牌生吐司", "实收金额": 7000.0, "销售数量": 250},
        {"商品名称": "原味牛角", "实收金额": 2000.0, "销售数量": 150},
        {"商品名称": "法式长棍", "实收金额": 800.0, "销售数量": 50},
        {"商品名称": "小饼干", "实收金额": 200.0, "销售数量": 10},
    ]
    df = pd.DataFrame(data)
    res = analyze_product_abc(df, top_a_pct=0.70, top_b_pct=0.90)

    assert res["total_products"] == 4
    assert res["total_revenue"] == 10000.0
    assert "A" in res["abc_summary"]
    assert "B" in res["abc_summary"]
    assert "C" in res["abc_summary"]

    # A class should have 招牌生吐司 (70%)
    assert res["abc_summary"]["A"]["product_count"] == 1
    assert res["abc_summary"]["A"]["top_products"][0]["name"] == "招牌生吐司"

    # Slow movers in C class
    assert len(res["slow_movers"]) > 0
    assert res["slow_movers"][0]["name"] == "小饼干"


def test_recharge_health_analysis():
    sales_detail_df = pd.DataFrame([
        {"实收金额": 100.0, "支付方式": "微信支付"},
        {"实收金额": 200.0, "支付方式": "储值卡支付"},
        {"实收金额": 100.0, "支付方式": "现金支付"},
    ])
    cards_detail_df = pd.DataFrame([
        {"充值金额": 500.0, "赠送金额": 50.0},
        {"充值金额": 100.0, "赠送金额": 0.0},
    ])

    res = analyze_recharge_health(sales_detail_df, cards_detail_df)
    assert res["total_sales_revenue"] == 400.0
    assert res["revenue_structure"]["direct_cash_amount"] == 200.0
    assert res["revenue_structure"]["card_consume_amount"] == 200.0
    assert res["revenue_structure"]["card_consume_ratio"] == "50.0%"

    assert res["recharge_summary"]["total_recharge_inflow"] == 600.0
    assert res["recharge_summary"]["total_gift_amount"] == 50.0
    assert res["actual_cash_inflow"] == 800.0  # 200 direct cash + 600 recharge inflow
    assert "health_evaluation" in res


def test_tool_exception_fallback(monkeypatch):
    # When underlying analysis function raises an unexpected exception, run_analysis catches it gracefully
    import modules.analysis_tools as at
    monkeypatch.setattr(at, "run_product_abc", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("底层计算崩溃")))

    res = ai.run_analysis.invoke({"analysis": "abc"})
    assert "error" in res
    assert "底层计算崩溃" in res["error"]


def test_langgraph_checkpointer_thread_session(monkeypatch):
    from langchain_core.messages import AIMessage, AIMessageChunk
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

    class FakeMemoryLLM(BaseChatModel):
        @property
        def _llm_type(self):
            return "fake"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="答复内容"))])

        def _stream(self, messages, stop=None, run_manager=None, **kwargs):
            yield ChatGenerationChunk(message=AIMessageChunk(content="测试答复"), text="测试答复")

    monkeypatch.setattr(ai, "ChatOpenAI", FakeMemoryLLM)

    # Test thread_id streaming
    async def run():
        tokens = []
        async for chunk in ai.stream_answer("你好", "上下文快照", thread_id="test_session_1"):
            if "token" in chunk:
                tokens.append(chunk["token"])
        return "".join(tokens)

    output = asyncio.run(run())
    assert output == "测试答复"
