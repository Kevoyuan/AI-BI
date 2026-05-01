"""
Agent evaluation test infrastructure.
Mock LLM provider for deterministic, fast agent tests.
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch


class MockProvider:
    """Programmable Mock LLM Provider — injects specific responses."""

    def __init__(self, responses=None, json_responses=None):
        """
        Args:
            responses:      dict[str, str]  — match by prefix in system/user prompt
            json_responses: dict[str, dict] — match by prefix, auto-serialised to JSON
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
            yield text[i : i + chunk_size]


@pytest.fixture
def mock_provider():
    return MockProvider()


@pytest.fixture
def sample_dataframes():
    """Return sample DataFrames simulating business data."""
    dates = pd.date_range("2026-04-01", periods=10, freq="D")
    sales = pd.DataFrame({
        "date": dates,
        "amount": np.random.randint(8000, 20000, 10).astype(float),
        "category": ["fresh_baked", "pastry", "beverages", "fresh_baked", "pastry"] * 2,
        "order_id": [f"ORD{i:04d}" for i in range(10)],
        "product": [f"Product_{i}" for i in range(10)],
    })
    waste = pd.DataFrame({
        "date": dates,
        "waste_amount": np.random.randint(100, 1000, 10).astype(float),
        "category": ["fresh_baked", "pastry"] * 5,
        "note": ["", "sample", "", "", "owner", "", "", "", "", ""],
        "reason": ["", "", "sample", "", "", "", "", "", "", ""],
    })
    return {"sales": sales, "waste": waste, "weather": pd.DataFrame()}


@pytest.fixture
def sample_history():
    return [
        {"role": "user", "content": "What was yesterday's revenue?"},
        {"role": "assistant", "content": "Yesterday's revenue was $15,230."},
    ]
