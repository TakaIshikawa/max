"""Tests for LLM client retry logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import anthropic
import pytest

from max.llm.client import _call_with_retry, structured_call, text_call
from pydantic import BaseModel


class TestCallWithRetry:
    """Tests for the _call_with_retry function."""

    def test_successful_call_on_first_attempt(self):
        """Should return result immediately on success."""
        mock_fn = MagicMock(return_value="success")

        result = _call_with_retry(mock_fn)

        assert result == "success"
        assert mock_fn.call_count == 1

    def test_retry_on_rate_limit_error_succeeds_on_second_attempt(self):
        """Should retry on RateLimitError and succeed on second attempt."""
        mock_fn = MagicMock()
        mock_fn.side_effect = [
            anthropic.RateLimitError("Rate limited", response=MagicMock(), body={}),
            "success",
        ]

        with patch("time.sleep") as mock_sleep:
            result = _call_with_retry(mock_fn, base_delay=1.0, backoff_factor=2.0)

        assert result == "success"
        assert mock_fn.call_count == 2
        mock_sleep.assert_called_once_with(1.0)  # First retry delay

    def test_retry_on_internal_server_error_succeeds_on_third_attempt(self):
        """Should retry on InternalServerError and succeed on third attempt."""
        mock_fn = MagicMock()
        mock_fn.side_effect = [
            anthropic.InternalServerError("Server error", response=MagicMock(), body={}),
            anthropic.InternalServerError("Server error", response=MagicMock(), body={}),
            "success",
        ]

        with patch("time.sleep") as mock_sleep:
            result = _call_with_retry(mock_fn, max_attempts=3, base_delay=1.0, backoff_factor=2.0)

        assert result == "success"
        assert mock_fn.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)  # First retry: 1.0 * 2^0 = 1.0
        mock_sleep.assert_any_call(2.0)  # Second retry: 1.0 * 2^1 = 2.0

    def test_retry_on_api_connection_error_succeeds_on_second_attempt(self):
        """Should retry on APIConnectionError (network error)."""
        mock_fn = MagicMock()
        mock_request = MagicMock()
        mock_fn.side_effect = [
            anthropic.APIConnectionError(message="Connection failed", request=mock_request),
            "success",
        ]

        with patch("time.sleep") as mock_sleep:
            result = _call_with_retry(mock_fn)

        assert result == "success"
        assert mock_fn.call_count == 2
        mock_sleep.assert_called_once()

    def test_bad_request_error_not_retried(self):
        """Should fail immediately on BadRequestError without retrying."""
        error = anthropic.BadRequestError("Bad request", response=MagicMock(), body={})
        mock_fn = MagicMock(side_effect=error)

        with pytest.raises(anthropic.BadRequestError):
            _call_with_retry(mock_fn)

        assert mock_fn.call_count == 1  # No retries

    def test_authentication_error_not_retried(self):
        """Should fail immediately on AuthenticationError without retrying."""
        error = anthropic.AuthenticationError("Invalid API key", response=MagicMock(), body={})
        mock_fn = MagicMock(side_effect=error)

        with pytest.raises(anthropic.AuthenticationError):
            _call_with_retry(mock_fn)

        assert mock_fn.call_count == 1  # No retries

    def test_permission_denied_error_not_retried(self):
        """Should fail immediately on PermissionDeniedError without retrying."""
        error = anthropic.PermissionDeniedError("Forbidden", response=MagicMock(), body={})
        mock_fn = MagicMock(side_effect=error)

        with pytest.raises(anthropic.PermissionDeniedError):
            _call_with_retry(mock_fn)

        assert mock_fn.call_count == 1  # No retries

    def test_exhausted_retries_raises_original_exception(self):
        """Should raise the original exception after exhausting all retries."""
        error = anthropic.RateLimitError("Rate limited", response=MagicMock(), body={})
        mock_fn = MagicMock(side_effect=error)

        with patch("time.sleep"):
            with pytest.raises(anthropic.RateLimitError):
                _call_with_retry(mock_fn, max_attempts=3)

        assert mock_fn.call_count == 3  # All attempts exhausted

    def test_exponential_backoff_timing(self):
        """Should use exponential backoff: 1s, 2s, 4s."""
        mock_fn = MagicMock()
        mock_fn.side_effect = [
            anthropic.RateLimitError("Rate limited", response=MagicMock(), body={}),
            anthropic.RateLimitError("Rate limited", response=MagicMock(), body={}),
            anthropic.RateLimitError("Rate limited", response=MagicMock(), body={}),
        ]

        with patch("time.sleep") as mock_sleep:
            with pytest.raises(anthropic.RateLimitError):
                _call_with_retry(mock_fn, max_attempts=3, base_delay=1.0, backoff_factor=2.0)

        assert mock_sleep.call_count == 2  # Sleep between attempts (not after last failure)
        mock_sleep.assert_any_call(1.0)  # First retry: 1.0 * 2^0
        mock_sleep.assert_any_call(2.0)  # Second retry: 1.0 * 2^1


class TestStructuredCallRetry:
    """Tests for retry logic in structured_call."""

    def test_structured_call_retries_on_rate_limit(self):
        """Should retry structured_call on rate limit error."""
        class DummyOutput(BaseModel):
            result: str

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [MagicMock(type="tool_use", input={"result": "success"})]

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("time.sleep"),
            patch("max.config.MAX_TOKEN_BUDGET", 0),
            patch("max.config.MAX_COST_BUDGET", 0.0),
        ):
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = [
                anthropic.RateLimitError("Rate limited", response=MagicMock(), body={}),
                mock_response,
            ]
            mock_get_client.return_value = mock_client

            result = structured_call(
                system="test",
                prompt="test",
                output_type=DummyOutput,
            )

            assert result.result == "success"
            assert mock_client.messages.create.call_count == 2

    def test_structured_call_does_not_retry_bad_request(self):
        """Should not retry structured_call on bad request error."""
        class DummyOutput(BaseModel):
            result: str

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("max.config.MAX_TOKEN_BUDGET", 0),
            patch("max.config.MAX_COST_BUDGET", 0.0),
        ):
            mock_client = MagicMock()
            error = anthropic.BadRequestError("Bad request", response=MagicMock(), body={})
            mock_client.messages.create.side_effect = error
            mock_get_client.return_value = mock_client

            with pytest.raises(anthropic.BadRequestError):
                structured_call(
                    system="test",
                    prompt="test",
                    output_type=DummyOutput,
                )

            assert mock_client.messages.create.call_count == 1

    def test_structured_call_budget_tracking_after_retry(self):
        """Budget tracking should work correctly after retries."""
        class DummyOutput(BaseModel):
            result: str

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 500
        mock_response.content = [MagicMock(type="tool_use", input={"result": "success"})]

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("max.llm.client.token_tracker") as mock_tracker,
            patch("time.sleep"),
            patch("max.config.MAX_TOKEN_BUDGET", 0),
            patch("max.config.MAX_COST_BUDGET", 0.0),
        ):
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = [
                anthropic.InternalServerError("Server error", response=MagicMock(), body={}),
                mock_response,
            ]
            mock_get_client.return_value = mock_client

            mock_tracker.total.return_value = 1500
            mock_tracker.is_over_budget.return_value = False

            result = structured_call(
                system="test",
                prompt="test",
                output_type=DummyOutput,
                stage="test_stage",
            )

            assert result.result == "success"
            # Budget tracking should be called with successful response tokens
            mock_tracker.record.assert_called_once_with("test_stage", 1000, 500)


class TestTextCallRetry:
    """Tests for retry logic in text_call."""

    def test_text_call_retries_on_internal_server_error(self):
        """Should retry text_call on internal server error."""
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [MagicMock(text="success")]

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("time.sleep"),
            patch("max.config.MAX_TOKEN_BUDGET", 0),
            patch("max.config.MAX_COST_BUDGET", 0.0),
        ):
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = [
                anthropic.InternalServerError("Server error", response=MagicMock(), body={}),
                mock_response,
            ]
            mock_get_client.return_value = mock_client

            result = text_call(system="test", prompt="test")

            assert result == "success"
            assert mock_client.messages.create.call_count == 2

    def test_text_call_does_not_retry_authentication_error(self):
        """Should not retry text_call on authentication error."""
        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("max.config.MAX_TOKEN_BUDGET", 0),
            patch("max.config.MAX_COST_BUDGET", 0.0),
        ):
            mock_client = MagicMock()
            error = anthropic.AuthenticationError("Invalid API key", response=MagicMock(), body={})
            mock_client.messages.create.side_effect = error
            mock_get_client.return_value = mock_client

            with pytest.raises(anthropic.AuthenticationError):
                text_call(system="test", prompt="test")

            assert mock_client.messages.create.call_count == 1

    def test_text_call_budget_tracking_after_retry(self):
        """Budget tracking should work correctly after retries."""
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 2000
        mock_response.usage.output_tokens = 1000
        mock_response.content = [MagicMock(text="success")]

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("max.llm.client.token_tracker") as mock_tracker,
            patch("time.sleep"),
            patch("max.config.MAX_TOKEN_BUDGET", 0),
            patch("max.config.MAX_COST_BUDGET", 0.0),
        ):
            mock_client = MagicMock()
            mock_request = MagicMock()
            mock_client.messages.create.side_effect = [
                anthropic.APIConnectionError(message="Connection failed", request=mock_request),
                mock_response,
            ]
            mock_get_client.return_value = mock_client

            mock_tracker.total.return_value = 3000
            mock_tracker.is_over_budget.return_value = False

            result = text_call(
                system="test",
                prompt="test",
                stage="test_stage",
            )

            assert result == "success"
            # Budget tracking should be called with successful response tokens
            mock_tracker.record.assert_called_once_with("test_stage", 2000, 1000)

    def test_text_call_exhausts_retries_raises_exception(self):
        """Should raise original exception after exhausting retries."""
        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("time.sleep"),
            patch("max.config.MAX_TOKEN_BUDGET", 0),
            patch("max.config.MAX_COST_BUDGET", 0.0),
        ):
            mock_client = MagicMock()
            error = anthropic.RateLimitError("Rate limited", response=MagicMock(), body={})
            mock_client.messages.create.side_effect = error
            mock_get_client.return_value = mock_client

            with pytest.raises(anthropic.RateLimitError):
                text_call(system="test", prompt="test")

            assert mock_client.messages.create.call_count == 3  # Default max_attempts
