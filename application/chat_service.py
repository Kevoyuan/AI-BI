"""Application service for the AI Assistant chat workflow.

This module coordinates routing and agent execution without importing
Streamlit. The page remains responsible for presenting the returned data.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd

from modules.ai_chat import get_ai_response_stream
from modules.context_builder import build_system_prompt
from modules.data_agent import DataAnalysisAgent
from modules.router_agent import RouterAgent


@dataclass
class ChatRequest:
    """Inputs required to resolve and execute one chat message."""

    prompt: str
    business_context: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)
    dataframes: Dict[str, pd.DataFrame] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """UI-agnostic result of one chat workflow."""

    skill: str
    skill_type: str
    reason: str = ""
    answer: Optional[str] = None
    answer_stream: Optional[Iterator[str]] = None
    code: Optional[str] = None
    chart: Any = None
    result_data: Any = None
    error: Optional[str] = None
    execution_log: List[str] = field(default_factory=list)


class ChatService:
    """Resolve a prompt and execute the selected text or code skill."""

    def __init__(self, router: Optional[RouterAgent] = None,
                 data_agent: Optional[DataAnalysisAgent] = None):
        self.router = router or RouterAgent()
        self.data_agent = data_agent or DataAnalysisAgent()

    def handle_message(self, request: ChatRequest) -> ChatResponse:
        """Return the routing decision and execution result for a prompt."""
        routing = self.router.resolve(
            request.prompt,
            request.business_context[:2000],
            request.history,
        )
        response = ChatResponse(
            skill=routing["skill"],
            skill_type=routing["skill_type"],
            reason=routing["reason"],
        )

        if response.skill_type == "code":
            try:
                result = self.data_agent.run(
                    request.prompt,
                    request.dataframes,
                    request.history,
                    skill_name=response.skill,
                    required_tables=routing["required_tables"],
                )
                response.answer = result.get("answer")
                response.code = result.get("code")
                response.chart = result.get("fig")
                response.result_data = result.get("result")
                response.error = result.get("error")
                response.execution_log = result.get("execution_log", [])
            except Exception as exc:
                response.error = str(exc)
                response.answer = f"Sorry, an error occurred: {exc}"
            return response

        try:
            system_prompt = build_system_prompt(request.business_context)
            response.answer_stream = get_ai_response_stream(
                request.prompt,
                system_prompt,
                request.history[:-1],
            )
        except Exception as exc:
            response.error = str(exc)
            response.answer = f"Sorry: {exc}"
        return response
