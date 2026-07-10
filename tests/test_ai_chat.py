"""Tests for the current public API in ``modules.ai_chat``."""
from unittest.mock import MagicMock, patch

from modules.ai_chat import get_ai_response, get_ai_response_stream


def test_get_ai_response_delegates_to_provider():
    provider = MagicMock()
    provider.chat.return_value = "Revenue was $15,230."

    with patch("modules.ai_chat.get_provider", return_value=provider):
        result = get_ai_response(
            "What was yesterday's revenue?",
            "You are a business assistant.",
            [{"role": "user", "content": "Hello"}],
        )

    assert result == "Revenue was $15,230."
    provider.chat.assert_called_once_with(
        "You are a business assistant.",
        [{"role": "user", "content": "Hello"}],
        "What was yesterday's revenue?",
    )


def test_get_ai_response_stream_yields_provider_chunks():
    provider = MagicMock()
    provider.chat_stream.return_value = iter(["Revenue was ", "$15,230."])

    with patch("modules.ai_chat.get_provider", return_value=provider):
        chunks = list(get_ai_response_stream("Revenue?", "system", []))

    assert chunks == ["Revenue was ", "$15,230."]
    provider.chat_stream.assert_called_once_with("system", [], "Revenue?")
