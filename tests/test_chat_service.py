"""Contract tests for the UI-independent chat application service."""
from unittest.mock import patch

import pandas as pd

from application.chat_service import ChatRequest, ChatService


class FakeRouter:
    def __init__(self, skill_type):
        self.skill_type = skill_type

    def resolve(self, query, context_summary, history):
        return {
            "skill": "deep_analysis" if self.skill_type == "code" else "daily_report",
            "skill_type": self.skill_type,
            "reason": "test route",
            "required_tables": ["sales"] if self.skill_type == "code" else None,
        }


class FakeDataAgent:
    def run(self, query, dataframes, history, skill_name, required_tables):
        return {
            "answer": "Analysis complete.",
            "code": "result = 1",
            "result": pd.DataFrame({"value": [1]}),
            "fig": "figure",
            "error": None,
            "execution_log": ["Execution succeeded"],
        }


def test_code_route_returns_renderable_response(sample_dataframes):
    service = ChatService(FakeRouter("code"), FakeDataAgent())

    response = service.handle_message(ChatRequest("Analyse sales", dataframes=sample_dataframes))

    assert response.skill == "deep_analysis"
    assert response.answer == "Analysis complete."
    assert response.code == "result = 1"
    assert response.chart == "figure"
    assert isinstance(response.result_data, pd.DataFrame)
    assert response.execution_log == ["Execution succeeded"]


def test_text_route_returns_stream_without_streamlit(sample_history):
    service = ChatService(FakeRouter("text"), FakeDataAgent())

    with patch("application.chat_service.build_system_prompt", return_value="system"), \
         patch("application.chat_service.get_ai_response_stream", return_value=iter(["hello", " world"])):
        response = service.handle_message(
            ChatRequest("What happened?", business_context="context", history=sample_history)
        )

    assert response.skill == "daily_report"
    assert response.answer is None
    assert response.answer_stream is not None
    assert "".join(response.answer_stream) == "hello world"
