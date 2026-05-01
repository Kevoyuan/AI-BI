"""
AI Chat Helpers
Thin wrappers around the LLM provider for the chat page.
"""
from typing import List, Dict, Generator

from modules.llm_provider import get_provider


def get_ai_response(
    prompt: str,
    system_prompt: str,
    history: List[Dict],
) -> str:
    """Non-streaming chat response."""
    provider = get_provider()
    return provider.chat(system_prompt, history, prompt)


def get_ai_response_stream(
    prompt: str,
    system_prompt: str,
    history: List[Dict],
) -> Generator[str, None, None]:
    """Streaming chat response — yields text chunks."""
    provider = get_provider()
    yield from provider.chat_stream(system_prompt, history, prompt)
