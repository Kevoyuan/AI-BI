"""
Agent evaluation test infrastructure.
Mock LLM provider for deterministic, fast agent tests.
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch


class MockProvider:
    """可编程的 Mock LLM Provider，用于注入特定响应。"""

    def __init__(self, responses=None, json_responses=None):
        """
        responses: dict[str, str] — 按 system_prompt 前缀匹配返回文本
        json_responses: dict[str, dict] — 按 prefix 匹配返回 dict（会自动 json.dumps）
        """
        self.responses = responses or {}
        self.json_responses = json_responses or {}
        self.generate_calls = []
        self.chat_calls = []
        self.chat_stream_calls = []

    def generate(self, system_prompt, user_prompt, json_mode=False):
        self.generate_calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "json_mode": json_mode,
        })
        if json_mode:
            for prefix, response_dict in self.json_responses.items():
                if prefix in system_prompt or prefix in user_prompt:
                    import json
                    return json.dumps(response_dict, ensure_ascii=False)
            return '{"skill": "daily_report", "reason": "mock default"}'
        for prefix, text in self.responses.items():
            if prefix in system_prompt or prefix in user_prompt:
                return text
        return "Mock response — no match found."

    def chat(self, system_prompt, history, message):
        self.chat_calls.append({
            "system_prompt": system_prompt,
            "history": history,
            "message": message,
        })
        for prefix, text in self.responses.items():
            if prefix in system_prompt or prefix in message:
                return text
        return f"Mock chat response to: {message[:50]}"

    def chat_stream(self, system_prompt, history, message):
        self.chat_stream_calls.append({
            "system_prompt": system_prompt,
            "history": history,
            "message": message,
        })
        text = self.chat(system_prompt, history, message)
        # Yield in chunks to simulate real streaming
        chunk_size = max(1, len(text) // 5)
        for i in range(0, len(text), chunk_size):
            yield text[i:i + chunk_size]


@pytest.fixture
def mock_provider():
    return MockProvider()


@pytest.fixture
def sample_dataframes():
    """返回示例 DataFrame，模拟业务数据。"""
    dates = pd.date_range("2026-04-01", periods=10, freq="D")
    sales = pd.DataFrame({
        "日期": dates,
        "实收金额": np.random.randint(8000, 20000, 10).astype(float),
        "商品分类": ["现烤", "西点", "饮品", "现烤", "西点"] * 2,
        "流水号": [f"LS{i:04d}" for i in range(10)],
        "商品名称": [f"产品{i}" for i in range(10)],
    })
    loss = pd.DataFrame({
        "日期": dates,
        "报损金额": np.random.randint(100, 1000, 10).astype(float),
        "商品分类": ["现烤", "西点"] * 5,
        "备注": ["", "试吃", "", "", "股东带走", "", "", "", "", ""],
        "报损原因": ["", "", "试吃", "", "", "", "", "", "", ""],
    })
    return {"sales": sales, "loss": loss, "weather": pd.DataFrame()}


@pytest.fixture
def sample_history():
    return [
        {"role": "user", "content": "昨天的销售额是多少？"},
        {"role": "assistant", "content": "昨天销售额为 15,230 元。"},
    ]
