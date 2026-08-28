"""Regression tests for the LangGraph AI assistant (L1 insight narrator).

These run inside the project venv that has langgraph + langchain-openai.
On a Python without those deps the whole module is skipped.
"""
import asyncio
import sys

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_openai")

sys.path.insert(0, ".")

from modules import ai_assistant as ai  # noqa: E402


def _patch_llm(monkeypatch, answer_text):
    """Replace the real DeepSeek client with a deterministic fake.

    The fake streams its answer through LangGraph's callback manager so the
    graph's ``stream_mode="messages"`` path (used by ``stream_answer``) is
    genuinely exercised, not just the ainvoke return value.
    """
    from langchain_core.callbacks import CallbackManagerForLLMRun
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, AIMessageChunk
    from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

    class FakeLLM(BaseChatModel):
        @property
        def _llm_type(self):
            return "fake"

        def bind_tools(self, tools, **kwargs):
            # The answer node calls `_build_llm().bind_tools(TOOLS)`; returning
            # self keeps the fake deterministic (no RunnableBinding surprises).
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=answer_text))])

        def _stream(self, messages, stop=None, run_manager=None, **kwargs):
            for ch in answer_text:
                yield ChatGenerationChunk(message=AIMessageChunk(content=ch), text=ch)

    monkeypatch.setattr(ai, "ChatOpenAI", FakeLLM)


def test_build_context_compresses_payload():
    payload = {
        "meta": {"range": "2026-08", "source": "银豹后台接口"},
        "kpis": {"revenue": 123456, "netProfit": -2000, "netProfitRate": -0.02},
        "alerts": [{"level": "warn", "title": "净利润为负"}],
        "topProducts": [{"name": "可颂", "amount": 12000}],
        "weekdayPattern": [{"weekday": "周二", "revenue": 8000}],
    }
    ctx = ai.build_context_from_payload(payload)
    assert "2026-08" in ctx
    assert "净利润为负" in ctx
    assert "可颂" in ctx
    assert "¥12.35万" in ctx  # money formatting


def test_build_context_handles_empty():
    assert "暂无" in ai.build_context_from_payload(None)


def test_system_prompt_includes_domain_knowledge():
    prompt = ai._build_system_prompt("## 当前时间范围：2026-08")
    assert "经营领域知识" in prompt
    assert "报废率" in prompt and "试吃" in prompt  # distilled from skills
    assert "2026-08" in prompt  # context snapshot still embedded


def test_graph_orchestration_returns_answer(monkeypatch):
    _patch_llm(monkeypatch, "这是一段测试回答。")
    from langchain_core.messages import HumanMessage

    async def run():
        graph = ai.get_graph()
        return await graph.ainvoke(
            {
                "messages": [HumanMessage(content="这家店有什么问题？")],
                "context": "## 当前时间范围：2026-08",
                "question": "这家店有什么问题？",
            }
        )

    result = asyncio.run(run())
    assert result["messages"][-1].content == "这是一段测试回答。"


def test_stream_answer_yields_tokens(monkeypatch):
    _patch_llm(monkeypatch, "逐字回答")

    async def run():
        items = []
        async for t in ai.stream_answer("hi", "ctx", []):
            items.append(t)
        return items

    items = asyncio.run(run())
    # stream_answer now yields {"token": ...} / {"status": ...} dicts for SSE
    assert "".join(i.get("token", "") for i in items) == "逐字回答"


def test_usage_summary_calculates_cache_savings(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "test-model")
    monkeypatch.setenv("DEEPSEEK_INPUT_USD_PER_MILLION", "1")
    monkeypatch.setenv("DEEPSEEK_CACHED_INPUT_USD_PER_MILLION", "0.1")
    monkeypatch.setenv("DEEPSEEK_OUTPUT_USD_PER_MILLION", "2")
    monkeypatch.setenv("DEEPSEEK_PRICE_VERSION", "test-prices")

    result = ai._usage_summary(
        {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 500}
    )
    assert result["model"] == "test-model"
    assert result["totalTokens"] == 1500
    assert result["cacheHit"] is True
    assert result["costUsd"] == 0.00164
    assert result["cacheSavingsUsd"] == 0.00036
    assert result["priceVersion"] == "test-prices"


def test_trim_payload_scopes():
    full = {
        "meta": {"range": "2026-08"},
        "kpis": {"revenue": 1},
        "daily": [{"日期": "2026-08-01", "实收金额": 100}] * 5,
        "raw": {"rows": [{"流水号": "A"}]},
        "unusedKey": 123,
    }
    s = ai._trim_payload(full, "summary")
    assert "kpis" in s and "unusedKey" not in s
    r = ai._trim_payload(full, "raw")
    assert r["raw"]["rows"] == [{"流水号": "A"}]
    assert ai._trim_payload(full, "full") is full

    # digest: pre-compressed TEXT snapshot (token-minimal)
    d = ai._trim_payload(full, "digest")
    assert isinstance(d.get("digest"), str) and "2026-08" in d["digest"]
    assert "daily" not in d  # no raw arrays in digest

    # chart: capped arrays, no huge sections
    c = ai._trim_payload(full, "chart")
    assert len(c["daily"]) == 5  # capped by limit
    big = {"meta": {}, "daily": list(range(200)), "weatherDaily": list(range(50))}
    c2 = ai._trim_payload(big, "chart")
    assert len(c2["daily"]) <= 60 and "weatherDaily" not in c2


def test_fetch_pospal_data_parses_date_spec(monkeypatch):
    """Tool 的 date_spec 解析 + scope 裁剪（不碰真实银豹网络）。"""
    import modules.dashboard_api as da

    captured = {}

    def fake_get(query, *, force_refresh=False):
        captured["query"] = query
        captured["refresh"] = force_refresh
        return {"meta": {"range": query.label()}, "kpis": {"revenue": 9}, "daily": []}

    monkeypatch.setattr(da, "get_dashboard_payload", fake_get)

    # ToolNode calls tools via .invoke(args_dict); default scope = digest (text)
    result = ai.fetch_pospal_data.invoke({"date_spec": {"preset": "week"}})
    assert captured["query"].date_from and captured["query"].date_to
    assert captured["refresh"] is False
    assert isinstance(result["digest"], str)  # token-minimal text by default

    # chart scope returns capped arrays for drawing
    chart = ai.fetch_pospal_data.invoke(
        {"date_spec": {"year": 2026, "month": 3}, "scope": "chart"}
    )
    assert "daily" in chart and "kpis" in chart

    ai.fetch_pospal_data.invoke(
        {"date_spec": {"year": 2026, "month": 3}, "refresh": True}
    )
    assert (captured["query"].year, captured["query"].month) == (2026, 3)
    assert captured["refresh"] is True

    # date range must also carry year/month (DashboardQuery requires them)
    ai.fetch_pospal_data.invoke(
        {"date_spec": {"date_from": "2026-03-01", "date_to": "2026-03-07"}}
    )
    assert captured["query"].date_from == "2026-03-01"
    assert captured["query"].date_to == "2026-03-07"
    assert (captured["query"].year, captured["query"].month) == (2026, 3)


def test_fetch_tool_archive_flag(monkeypatch):
    """archive=True 应把涉及的月份交给 pospal_live_data.archive_month。"""
    import modules.dashboard_api as da
    import modules.pospal_live_data as pl

    monkeypatch.setattr(
        da, "get_dashboard_payload", lambda q, *, force_refresh=False: {"meta": {}, "kpis": {}}
    )
    archived = []
    monkeypatch.setattr(pl, "archive_month", lambda y, m: archived.append((y, m)) or True)

    ai.fetch_pospal_data.invoke(
        {"date_spec": {"year": 2026, "month": 3}, "archive": True}
    )
    assert (2026, 3) in archived

    # 跨月日期区间 → 覆盖两个月份
    ai.fetch_pospal_data.invoke(
        {
            "date_spec": {"date_from": "2026-02-25", "date_to": "2026-03-05"},
            "archive": True,
        }
    )
    assert (2026, 2) in archived and (2026, 3) in archived


def test_run_analysis_dispatch(monkeypatch):
    """run_analysis 按 analysis 分发到 forecast / weather。"""
    import modules.analysis_tools as at

    called = {}
    monkeypatch.setattr(
        at,
        "run_forecast",
        lambda ds, horizon: called.update({"kind": "forecast", "h": horizon}) or {"ok": 1},
    )
    monkeypatch.setattr(
        at, "run_weather_impact", lambda ds: called.update({"kind": "weather"}) or {"ok": 1}
    )

    ai.run_analysis.invoke(
        {"analysis": "forecast", "date_spec": {"preset": "month"}, "horizon": "tomorrow"}
    )
    assert called["kind"] == "forecast" and called["h"] == "tomorrow"

    ai.run_analysis.invoke({"analysis": "weather", "date_spec": {}})
    assert called["kind"] == "weather"

    with pytest.raises(ValueError):
        ai.run_analysis.invoke({"analysis": "bogus", "date_spec": {}})
