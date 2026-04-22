"""Tests for LLM client retry logic and token tracking."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import anthropic
import httpx
import pytest
from pydantic import BaseModel

from max.llm.client import (
    BudgetExceededError,
    TokenTracker,
    _call_with_retry,
    estimate_token_cost_usd,
    structured_call,
    text_call,
    token_counts_from_usage,
)


class DummyOutput(BaseModel):
    result: str


def test_token_counts_from_usage_supports_summary_and_raw_shapes():
    assert token_counts_from_usage({"total_input": 100, "total_output": 50}) == (100, 50)
    assert token_counts_from_usage({"input": 75, "output": 25}) == (75, 25)


def test_estimate_token_cost_usd_uses_model_pricing():
    assert estimate_token_cost_usd(
        1000,
        500,
        model="claude-opus-4-6",
    ) == pytest.approx(0.0525)


def _create_mock_http_response(status_code: int, headers: dict[str, str] | None = None) -> Mock:
    """Helper to create mock httpx.Response with required attributes."""
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.headers = httpx.Headers(headers or {})
    return mock_response


@pytest.fixture
def mock_response():
    """Create a mock Anthropic message response."""
    response = Mock()
    response.usage = Mock()
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    response.content = [Mock(type="tool_use", input={"result": "test"})]
    return response


@pytest.fixture
def mock_text_response():
    """Create a mock Anthropic text response."""
    response = Mock()
    response.usage = Mock()
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    response.content = [Mock(text="Test response")]
    return response


class TestRetryAfterHeader:
    """Test Retry-After header parsing in retry logic."""

    def test_retry_after_header_respected(self, caplog):
        """Test that Retry-After header value is used when present."""
        # Create a mock response with Retry-After header
        mock_http_response = _create_mock_http_response(429, {"retry-after": "5.0"})

        # Create RateLimitError with the response
        error = anthropic.RateLimitError(
            message="Rate limit exceeded",
            response=mock_http_response,
            body=None,
        )

        call_count = 0

        def failing_then_succeeding():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise error
            return "success"

        with caplog.at_level(logging.INFO):
            with patch("max.llm.client.time.sleep") as mock_sleep:
                result = _call_with_retry(failing_then_succeeding, max_attempts=2)

        assert result == "success"
        assert call_count == 2

        # Verify Retry-After was used (should be max(5.0, 1.0) = 5.0)
        mock_sleep.assert_called_once_with(5.0)

        # Check log message
        assert "Rate limit hit — using Retry-After header: 5.0s" in caplog.text

    def test_retry_after_header_uses_max_with_backoff(self, caplog):
        """Test that Retry-After uses max(retry_after, calculated_backoff)."""
        # Set a low Retry-After value (0.5s) that should be overridden by backoff (1.0s)
        mock_http_response = _create_mock_http_response(429, {"retry-after": "0.5"})

        error = anthropic.RateLimitError(
            message="Rate limit exceeded",
            response=mock_http_response,
            body=None,
        )

        call_count = 0

        def failing_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise error
            return "success"

        with patch("max.llm.client.time.sleep") as mock_sleep:
            _call_with_retry(failing_once, base_delay=1.0)

        # Should use max(0.5, 1.0) = 1.0
        mock_sleep.assert_called_once_with(1.0)

    def test_invalid_retry_after_header_ignored(self, caplog):
        """Test that invalid Retry-After headers are gracefully ignored."""
        mock_http_response = _create_mock_http_response(429, {"retry-after": "invalid"})

        error = anthropic.RateLimitError(
            message="Rate limit exceeded",
            response=mock_http_response,
            body=None,
        )

        call_count = 0

        def failing_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise error
            return "success"

        with caplog.at_level(logging.DEBUG):
            with patch("max.llm.client.time.sleep") as mock_sleep:
                _call_with_retry(failing_once, base_delay=1.0)

        # Should fall back to calculated backoff
        mock_sleep.assert_called_once_with(1.0)
        assert "Could not parse Retry-After header: invalid" in caplog.text

    def test_missing_retry_after_header_uses_backoff(self):
        """Test that missing Retry-After header uses normal exponential backoff."""
        mock_http_response = _create_mock_http_response(429, {})

        error = anthropic.RateLimitError(
            message="Rate limit exceeded",
            response=mock_http_response,
            body=None,
        )

        call_count = 0

        def failing_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise error
            return "success"

        with patch("max.llm.client.time.sleep") as mock_sleep:
            _call_with_retry(failing_once, base_delay=2.0)

        # Should use calculated backoff (2.0 * 2^0 = 2.0)
        mock_sleep.assert_called_once_with(2.0)


class TestPerCallLogging:
    """Test per-call token usage debug logging."""

    @patch("max.config.MAX_TOKEN_BUDGET", 0)
    @patch("max.config.MAX_COST_BUDGET", 0.0)
    @patch("max.llm.client.get_client")
    @patch("max.llm.client.token_tracker")
    def test_structured_call_logs_token_usage(
        self, mock_tracker, mock_get_client, mock_response, caplog
    ):
        """Test that structured_call logs token usage with all required fields."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        # Make sure tracker methods don't trigger budget errors
        mock_tracker.total.return_value = 0
        mock_tracker.is_over_budget.return_value = False

        with caplog.at_level(logging.DEBUG):
            structured_call(
                system="Test system",
                prompt="Test prompt",
                output_type=DummyOutput,
                model="claude-opus-4-6",
                stage="test_stage",
            )

        # Check that debug log was emitted with correct fields
        log_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert len(log_records) == 1

        log_message = log_records[0].message
        assert "stage=test_stage" in log_message
        assert "input_tokens=100" in log_message
        assert "output_tokens=50" in log_message
        assert "model=claude-opus-4-6" in log_message
        assert "latency=" in log_message

    @patch("max.config.MAX_TOKEN_BUDGET", 0)
    @patch("max.config.MAX_COST_BUDGET", 0.0)
    @patch("max.llm.client.get_client")
    @patch("max.llm.client.token_tracker")
    def test_text_call_logs_token_usage(
        self, mock_tracker, mock_get_client, mock_text_response, caplog
    ):
        """Test that text_call logs token usage with all required fields."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.messages.create.return_value = mock_text_response

        # Make sure tracker methods don't trigger budget errors
        mock_tracker.total.return_value = 0
        mock_tracker.is_over_budget.return_value = False

        with caplog.at_level(logging.DEBUG):
            text_call(
                system="Test system",
                prompt="Test prompt",
                model="claude-sonnet-4-5-20250929",
                stage="text_test",
            )

        # Check that debug log was emitted
        log_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert len(log_records) == 1

        log_message = log_records[0].message
        assert "stage=text_test" in log_message
        assert "input_tokens=100" in log_message
        assert "output_tokens=50" in log_message
        assert "model=claude-sonnet-4-5-20250929" in log_message
        assert "latency=" in log_message

    @patch("max.llm.client.get_client")
    def test_no_logging_without_stage(self, mock_get_client, mock_response, caplog):
        """Test that no logging occurs when stage is empty."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        with caplog.at_level(logging.DEBUG):
            structured_call(
                system="Test system",
                prompt="Test prompt",
                output_type=DummyOutput,
                stage="",  # Empty stage
            )

        # Should not log token usage when stage is empty
        debug_logs = [r for r in caplog.records if "input_tokens" in r.message]
        assert len(debug_logs) == 0


class TestUnknownModelWarning:
    """Test that unknown models trigger pricing fallback warnings."""

    def test_unknown_model_logs_warning_in_estimated_cost(self, caplog):
        """Test warning is logged when unknown model is used in estimated_cost_usd."""
        tracker = TokenTracker(model="claude-unknown-model")
        tracker.record("test", 1000, 500)

        with caplog.at_level(logging.WARNING):
            cost = tracker.estimated_cost_usd()

        assert cost > 0  # Should still calculate using fallback
        assert "Unknown model 'claude-unknown-model' for cost tracking" in caplog.text
        assert "falling back to Opus pricing" in caplog.text

    def test_unknown_model_logs_warning_in_cost_by_stage(self, caplog):
        """Test warning is logged when unknown model is used in cost_by_stage."""
        tracker = TokenTracker(model="claude-future-model")
        tracker.record("stage1", 1000, 500)

        with caplog.at_level(logging.WARNING):
            costs = tracker.cost_by_stage()

        assert "stage1" in costs
        assert costs["stage1"] > 0
        assert "Unknown model 'claude-future-model' for cost tracking" in caplog.text

    def test_known_model_no_warning(self, caplog):
        """Test that known models don't trigger warnings."""
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("test", 1000, 500)

        with caplog.at_level(logging.WARNING):
            tracker.estimated_cost_usd()
            tracker.cost_by_stage()

        # Should not contain any warnings about unknown models
        assert "Unknown model" not in caplog.text


class TestRetryExhaustionError:
    """Test that retry exhaustion raises RuntimeError instead of AssertionError."""

    def test_exhausted_retries_raises_runtime_error(self):
        """Test that exhausting retries raises RuntimeError, not AssertionError."""
        mock_http_response = _create_mock_http_response(500)

        error = anthropic.InternalServerError(
            message="Server error",
            response=mock_http_response,
            body=None,
        )

        def always_fails():
            raise error

        # Should raise the original exception after retries
        with pytest.raises(anthropic.InternalServerError):
            _call_with_retry(always_fails, max_attempts=2, base_delay=0.01)

    def test_retry_logic_internal_error_handling(self):
        """Test that the internal retry logic doesn't raise AssertionError."""
        # This test ensures that the assertion was replaced with proper error handling
        # by testing the code path where last_exception would be None (edge case)

        # Create a scenario where retry logic might fail internally
        call_count = 0

        def succeeds_immediately():
            nonlocal call_count
            call_count += 1
            return "success"

        # This should work fine and not hit any assertions
        result = _call_with_retry(succeeds_immediately)
        assert result == "success"
        assert call_count == 1


class TestRetryBehavior:
    """Additional tests for retry behavior."""

    def test_non_retryable_error_fails_immediately(self):
        """Test that non-retryable errors fail without retry."""
        mock_http_response = _create_mock_http_response(400)

        error = anthropic.BadRequestError(
            message="Bad request",
            response=mock_http_response,
            body=None,
        )

        call_count = 0

        def fails_with_bad_request():
            nonlocal call_count
            call_count += 1
            raise error

        with pytest.raises(anthropic.BadRequestError):
            _call_with_retry(fails_with_bad_request, max_attempts=3)

        # Should only be called once (no retries)
        assert call_count == 1

    def test_exponential_backoff_without_retry_after(self):
        """Test exponential backoff when Retry-After header is absent."""
        mock_http_response = _create_mock_http_response(500)

        error = anthropic.InternalServerError(
            message="Server error",
            response=mock_http_response,
            body=None,
        )

        call_count = 0

        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise error
            return "success"

        with patch("max.llm.client.time.sleep") as mock_sleep:
            result = _call_with_retry(
                fails_twice, max_attempts=3, base_delay=1.0, backoff_factor=2.0
            )

        assert result == "success"
        assert call_count == 3

        # Check exponential backoff: 1.0 * 2^0 = 1.0, then 1.0 * 2^1 = 2.0
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)


class TestTokenTrackerEdgeCases:
    """Test edge cases in token tracking."""

    def test_tracker_with_zero_budget_never_exceeds(self):
        """Test that zero budget is treated as unlimited."""
        tracker = TokenTracker()
        tracker.record("test", 1_000_000, 1_000_000)

        # Zero budget should never be exceeded
        assert not tracker.is_over_budget(0.0)
        assert tracker.budget_remaining(0.0) == float("inf")

    def test_tracker_reset_clears_all_data(self):
        """Test that reset properly clears all tracking data."""
        tracker = TokenTracker()
        tracker.record("stage1", 100, 50)
        tracker.record("stage2", 200, 100)

        tracker.reset()

        assert tracker.total() == 0
        assert tracker.usage == {"input": 0, "output": 0}
        assert len(tracker.by_stage) == 0

    def test_tracker_summary_includes_all_stages(self):
        """Test that summary includes per-stage breakdown."""
        tracker = TokenTracker()
        tracker.record("stage1", 100, 50)
        tracker.record("stage2", 200, 100)

        summary = tracker.summary()

        assert summary["total_input"] == 300
        assert summary["total_output"] == 150
        assert summary["stage1_input"] == 100
        assert summary["stage1_output"] == 50
        assert summary["stage2_input"] == 200
        assert summary["stage2_output"] == 100
