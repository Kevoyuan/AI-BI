"""
LLM Provider abstraction layer.

Supports DeepSeek (OpenAI-compatible) and Google Gemini backends
through a unified interface, making it trivial to swap providers
without touching calling code.
"""
import os
import logging
from abc import ABC, abstractmethod
from typing import Generator, List, Dict

logger = logging.getLogger(__name__)


# ── Abstract base ─────────────────────────────────────────────────────────────

class BaseProvider(ABC):
    """Common interface all LLM providers must implement."""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str,
                 json_mode: bool = False) -> str:
        """Single-turn generation. Returns the full response text."""

    @abstractmethod
    def chat(self, system_prompt: str, history: List[Dict],
             message: str) -> str:
        """Multi-turn chat. `history` format: [{"role": "user/assistant", "content": "..."}]"""

    @abstractmethod
    def chat_stream(self, system_prompt: str, history: List[Dict],
                    message: str) -> Generator[str, None, None]:
        """Streaming multi-turn chat. Yields text chunks."""


# ── DeepSeek (OpenAI-compatible) ─────────────────────────────────────────────

class DeepSeekProvider(BaseProvider):
    """
    Wraps the DeepSeek API using the official OpenAI Python client.
    Works with any OpenAI-compatible endpoint (e.g. local Ollama, vLLM).
    """

    def __init__(self, api_key: str,
                 base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-chat"):
        import httpx
        from openai import OpenAI

        # trust_env=False prevents proxy leakage in production
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            http_client=httpx.Client(trust_env=False),
        )
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str,
                 json_mode: bool = False) -> str:
        messages = [
            {"role": "system",  "content": system_prompt},
            {"role": "user",    "content": user_prompt},
        ]
        kwargs: dict = {"model": self.model, "messages": messages}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def chat(self, system_prompt: str, history: List[Dict],
             message: str) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            role = "assistant" if h["role"] == "assistant" else "user"
            messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": message})

        response = self.client.chat.completions.create(
            model=self.model, messages=messages
        )
        return response.choices[0].message.content

    def chat_stream(self, system_prompt: str, history: List[Dict],
                    message: str) -> Generator[str, None, None]:
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            role = "assistant" if h["role"] == "assistant" else "user"
            messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": message})

        stream = self.client.chat.completions.create(
            model=self.model, messages=messages, stream=True
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# ── Google Gemini ─────────────────────────────────────────────────────────────

class GeminiProvider(BaseProvider):
    """
    Wraps Google Gemini via the `google-generativeai` SDK.
    History is converted to Gemini's {role, parts} format internally.
    """

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.genai = genai
        self.model_name = model

    def generate(self, system_prompt: str, user_prompt: str,
                 json_mode: bool = False) -> str:
        model = self.genai.GenerativeModel(
            self.model_name, system_instruction=system_prompt
        )
        gen_config = {}
        if json_mode:
            gen_config["response_mime_type"] = "application/json"

        response = model.generate_content(user_prompt, generation_config=gen_config)
        return response.text

    def chat(self, system_prompt: str, history: List[Dict],
             message: str) -> str:
        model = self.genai.GenerativeModel(
            self.model_name, system_instruction=system_prompt
        )
        chat_session = model.start_chat(history=self._to_gemini_history(history))
        return chat_session.send_message(message).text

    def chat_stream(self, system_prompt: str, history: List[Dict],
                    message: str) -> Generator[str, None, None]:
        model = self.genai.GenerativeModel(
            self.model_name, system_instruction=system_prompt
        )
        chat_session = model.start_chat(history=self._to_gemini_history(history))
        for chunk in chat_session.send_message(message, stream=True):
            if chunk.text:
                yield chunk.text

    @staticmethod
    def _to_gemini_history(history: List[Dict]) -> List[Dict]:
        """Convert standard message history to Gemini's format."""
        result = []
        for msg in history[-20:]:
            if msg.get("content"):
                role = "user" if msg["role"] == "user" else "model"
                result.append({"role": role, "parts": [msg["content"]]})
        return result


# ── Factory ───────────────────────────────────────────────────────────────────

def get_provider() -> BaseProvider:
    """
    Factory function: reads LLM_PROVIDER env var and returns the
    appropriate provider. Defaults to DeepSeek.

    Usage:
        provider = get_provider()
        answer = provider.generate(system, user)
    """
    provider_type = os.getenv("LLM_PROVIDER", "deepseek").lower()

    if provider_type == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment.")
        logger.info("Using Gemini provider: %s", model)
        return GeminiProvider(api_key=api_key, model=model)

    # Default: DeepSeek
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY is not set in environment.")
    logger.info("Using DeepSeek provider: %s @ %s", model, base_url)
    return DeepSeekProvider(api_key=api_key, base_url=base_url, model=model)
