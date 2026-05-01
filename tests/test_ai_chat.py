"""
AI Chat module tests — response quality, fallback, streaming, retry logic.
All LLM calls use MockProvider for deterministic behaviour.
"""
import pytest
from unittest.mock import MagicMock, patch
from modules.ai_chat import (
    _validate_response_quality,
    _generate_fallback_response,
    _generate_enhanced_fallback_response,
    _generate_response_with_retry,
    _enhance_system_prompt,
    get_ai_response,
    get_ai_response_stream,
)


class TestResponseQualityValidation:
    """_validate_response_quality gating logic."""

    def test_accepts_valid_business_response(self):
        """Response with sufficient length and business terms → passes."""
        response = "Based on the sales data, yesterday's revenue was $15,230, up 5% from the prior day."
        assert _validate_response_quality(response, "revenue") is True

    def test_rejects_short_response(self):
        assert _validate_response_quality("Here.", "revenue") is False

    def test_rejects_empty_response(self):
        assert _validate_response_quality("", "anything") is False
        assert _validate_response_quality(None, "anything") is False

    def test_rejects_ai_apology_response(self):
        """Responses with AI apology patterns → rejected."""
        responses = [
            "As an AI, I cannot provide real-time sales data.",
            "I'm sorry, I don't have access to that information.",
            "I understand your question, but I don't have the data.",
        ]
        for resp in responses:
            assert _validate_response_quality(resp, "revenue") is False, \
                f"Should reject: '{resp}'"


class TestFallbackResponses:
    """Fallback functions output format."""

    def test_fallback_includes_question_and_error(self):
        result = _generate_fallback_response("revenue analysis", "API timeout")
        assert "revenue analysis" in result
        assert "API timeout" in result

    def test_fallback_without_error(self):
        result = _generate_fallback_response("customer data")
        assert "customer data" in result


class TestRetryLogic:
    """_generate_response_with_retry fault tolerance."""

    def test_returns_on_first_success(self):
        """Quality passes → single call, no retry."""
        provider = MagicMock()
        valid_response = "Based on sales data, yesterday revenue was $15,000, customer count 350."
        provider.chat.return_value = valid_response

        result = _generate_response_with_retry(
            provider, "system prompt", [], "revenue query"
        )

        assert result == valid_response
        assert provider.chat.call_count == 1

    def test_uses_simple_fallback_on_exception(self):
        """LLM exception → basic fallback with error info."""
        provider = MagicMock()
        provider.chat.side_effect = RuntimeError("network error")

        result = _generate_response_with_retry(
            provider, "system prompt", [], "revenue query", max_retries=0
        )

        assert "network error" in result


class TestGetAIResponse:
    """Integration: get_ai_response end-to-end."""

    def test_full_flow_with_mock(self):
        mock_provider = MagicMock()
        mock_provider.chat.return_value = \
            "Based on the data, yesterday's revenue was $15,230, 350 customers, avg ticket $43.50."

        with patch("modules.ai_chat._init_provider", return_value=mock_provider):
            result = get_ai_response(
                "Yesterday's revenue?",
                "You are a business assistant.",
                [{"role": "user", "content": "Hello"}],
            )

        assert "15,230" in result
        mock_provider.chat.assert_called_once()

    def test_returns_fallback_when_no_provider(self):
        with patch("modules.ai_chat._init_provider", return_value=None):
            result = get_ai_response("revenue", "system", [])

        assert "LLM Provider" in result


class TestGetAIResponseStream:
    """Streaming: get_ai_response_stream chunk behaviour."""

    def test_yields_chunks(self):
        mock_provider = MagicMock()
        full_text = "Based on analysis, revenue was $15,230."
        mock_provider.chat_stream.return_value = iter([
            "Based on analysis, ", "revenue was $15,230."
        ])

        with patch("modules.ai_chat._init_provider", return_value=mock_provider):
            chunks = list(get_ai_response_stream("revenue", "system", []))

        assert len(chunks) == 2
        assert "".join(chunks) == full_text

    def test_fallback_when_no_provider(self):
        with patch("modules.ai_chat._init_provider", return_value=None):
            chunks = list(get_ai_response_stream("revenue", "system", []))

        assert len(chunks) == 1
        assert "LLM Provider" in chunks[0]

    def test_error_yields_fallback(self):
        mock_provider = MagicMock()
        mock_provider.chat_stream.side_effect = RuntimeError("stream interrupted")

        with patch("modules.ai_chat._init_provider", return_value=mock_provider):
            chunks = list(get_ai_response_stream("revenue", "system", []))

        assert len(chunks) == 1
        assert "stream interrupted" in chunks[0]
