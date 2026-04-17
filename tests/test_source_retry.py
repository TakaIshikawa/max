"""Tests for source adapter retry utilities."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from max.sources.errors import (
    SourceAuthError,
    SourceParseError,
    SourceRateLimitError,
    SourceTransientError,
)
from max.sources.retry import retry_async, with_retry


class TestWithRetryDecorator:
    """Tests for the with_retry decorator."""

    @pytest.mark.asyncio
    async def test_successful_call_on_first_attempt(self):
        """Should return immediately on success without retries."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.1, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            return {"status": "ok"}

        result = await fetch_data()
        assert result == {"status": "ok"}
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_successful_call_after_transient_failures(self):
        """Should retry on transient errors and eventually succeed."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.05, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise SourceTransientError(
                    "Server error", adapter_name="test", retry_after=0.01
                )
            return {"status": "ok"}

        result = await fetch_data()
        assert result == {"status": "ok"}
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises_final_error(self):
        """Should raise the final exception after exhausting all retries."""
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.05, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            raise SourceTransientError("Persistent error", adapter_name="test")

        with pytest.raises(SourceTransientError, match="Persistent error"):
            await fetch_data()

        # Should try: initial + 2 retries = 3 total attempts
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_backoff_timing_increases_exponentially(self):
        """Should use exponential backoff with increasing delays."""
        call_times = []

        @with_retry(max_retries=3, base_delay=0.1, adapter_name="test")
        async def fetch_data():
            call_times.append(time.monotonic())
            raise SourceTransientError("Error", adapter_name="test")

        with pytest.raises(SourceTransientError):
            await fetch_data()

        # Should have 4 calls (initial + 3 retries)
        assert len(call_times) == 4

        # Check that delays are increasing (with jitter tolerance)
        # Delay 1: ~0.1s, Delay 2: ~0.2s, Delay 3: ~0.4s
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        delay3 = call_times[3] - call_times[2]

        # Allow 50% jitter tolerance
        assert 0.05 <= delay1 <= 0.15, f"delay1={delay1}"
        assert 0.1 <= delay2 <= 0.3, f"delay2={delay2}"
        assert 0.2 <= delay3 <= 0.6, f"delay3={delay3}"

        # Verify exponential growth (delay2 > delay1, delay3 > delay2)
        # Account for jitter by checking ranges overlap
        assert delay2 >= delay1 * 0.8  # Allow some jitter variance
        assert delay3 >= delay2 * 0.8

    @pytest.mark.asyncio
    async def test_non_retryable_auth_error_raised_immediately(self):
        """Should raise auth errors immediately without retrying."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.1, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            raise SourceAuthError("Unauthorized", adapter_name="test")

        with pytest.raises(SourceAuthError, match="Unauthorized"):
            await fetch_data()

        # Should only call once (no retries)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_non_retryable_parse_error_raised_immediately(self):
        """Should raise parse errors immediately without retrying."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.1, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            raise SourceParseError("Invalid JSON", adapter_name="test")

        with pytest.raises(SourceParseError, match="Invalid JSON"):
            await fetch_data()

        # Should only call once (no retries)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_rate_limit_error_uses_retry_after(self):
        """Should respect retry_after from rate limit errors."""
        call_times = []

        @with_retry(max_retries=1, base_delay=0.1, adapter_name="test")
        async def fetch_data():
            call_times.append(time.monotonic())
            if len(call_times) < 2:
                raise SourceRateLimitError(
                    "Rate limited", adapter_name="test", retry_after=0.2
                )
            return {"status": "ok"}

        result = await fetch_data()
        assert result == {"status": "ok"}
        assert len(call_times) == 2

        # Should use retry_after (0.2s) instead of base_delay
        delay = call_times[1] - call_times[0]
        assert 0.18 <= delay <= 0.25  # Allow small timing variance

    @pytest.mark.asyncio
    async def test_httpx_request_error_is_retryable(self):
        """Should retry on httpx.RequestError (network failures)."""
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.05, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.RequestError("Connection failed")
            return {"status": "ok"}

        result = await fetch_data()
        assert result == {"status": "ok"}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_httpx_timeout_error_is_retryable(self):
        """Should retry on httpx.TimeoutException."""
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.05, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("Request timed out")
            return {"status": "ok"}

        result = await fetch_data()
        assert result == {"status": "ok"}
        assert call_count == 2


class TestRetryAsync:
    """Tests for the retry_async function."""

    @pytest.mark.asyncio
    async def test_successful_call_on_first_attempt(self):
        """Should return immediately on success without retries."""
        call_count = 0

        async def fetch_data(value: str):
            nonlocal call_count
            call_count += 1
            return {"result": value}

        result = await retry_async(
            fetch_data,
            "test",
            max_retries=3,
            base_delay=0.1,
            adapter_name="test",
        )
        assert result == {"result": "test"}
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_successful_call_after_transient_failures(self):
        """Should retry on transient errors and eventually succeed."""
        call_count = 0

        async def fetch_data():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise SourceTransientError("Server error", adapter_name="test")
            return {"status": "ok"}

        result = await retry_async(
            fetch_data,
            max_retries=3,
            base_delay=0.05,
            adapter_name="test",
        )
        assert result == {"status": "ok"}
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises_final_error(self):
        """Should raise the final exception after exhausting all retries."""
        call_count = 0

        async def fetch_data():
            nonlocal call_count
            call_count += 1
            raise SourceRateLimitError("Rate limited", adapter_name="test")

        with pytest.raises(SourceRateLimitError, match="Rate limited"):
            await retry_async(
                fetch_data,
                max_retries=2,
                base_delay=0.05,
                adapter_name="test",
            )

        # Should try: initial + 2 retries = 3 total attempts
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_errors_raised_immediately(self):
        """Should raise non-retryable errors immediately."""
        call_count = 0

        async def fetch_data():
            nonlocal call_count
            call_count += 1
            raise SourceAuthError("Forbidden", adapter_name="test")

        with pytest.raises(SourceAuthError, match="Forbidden"):
            await retry_async(
                fetch_data,
                max_retries=3,
                base_delay=0.1,
                adapter_name="test",
            )

        # Should only call once (no retries)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_passes_args_and_kwargs_correctly(self):
        """Should correctly pass positional and keyword arguments."""

        async def fetch_data(pos_arg: str, *, kw_arg: int):
            return {"pos": pos_arg, "kw": kw_arg}

        result = await retry_async(
            fetch_data,
            "hello",
            kw_arg=42,
            max_retries=1,
            base_delay=0.1,
            adapter_name="test",
        )
        assert result == {"pos": "hello", "kw": 42}


class TestRetryLogging:
    """Tests for retry logging behavior."""

    @pytest.mark.asyncio
    async def test_logs_retry_attempts(self, caplog):
        """Should log each retry attempt with relevant details."""
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.05, adapter_name="test_adapter")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise SourceTransientError("Server error", adapter_name="test")
            return {"status": "ok"}

        with caplog.at_level("WARNING"):
            result = await fetch_data()

        assert result == {"status": "ok"}

        # Should have 2 retry log messages
        retry_logs = [r for r in caplog.records if "retry attempt" in r.message]
        assert len(retry_logs) == 2

        # Check log format
        assert "test_adapter" in retry_logs[0].message
        assert "retry attempt 1/2" in retry_logs[0].message
        assert "retry attempt 2/2" in retry_logs[1].message

    @pytest.mark.asyncio
    async def test_logs_exhausted_retries(self, caplog):
        """Should log when retries are exhausted."""

        @with_retry(max_retries=1, base_delay=0.05, adapter_name="test_adapter")
        async def fetch_data():
            raise SourceTransientError("Persistent error", adapter_name="test")

        with caplog.at_level("WARNING"):
            with pytest.raises(SourceTransientError):
                await fetch_data()

        # Should have exhausted retries log
        exhausted_logs = [r for r in caplog.records if "exhausted retries" in r.message]
        assert len(exhausted_logs) == 1
        assert "test_adapter" in exhausted_logs[0].message
        assert "2 attempts" in exhausted_logs[0].message


class TestRetryJitter:
    """Tests for retry jitter behavior."""

    @pytest.mark.asyncio
    async def test_jitter_varies_delay(self):
        """Should apply random jitter to delays (0.5-1.0 multiplier)."""
        delays = []

        for _ in range(10):
            call_times = []

            @with_retry(max_retries=1, base_delay=1.0, adapter_name="test")
            async def fetch_data():
                call_times.append(time.monotonic())
                if len(call_times) < 2:
                    raise SourceTransientError("Error", adapter_name="test")
                return "ok"

            await fetch_data()

            delay = call_times[1] - call_times[0]
            delays.append(delay)

        # All delays should be within jittered range: 0.5s to 1.0s
        assert all(0.5 <= d <= 1.0 for d in delays), f"delays={delays}"

        # Delays should vary (not all the same)
        # Check that we have at least some variance
        unique_delays = len(set(round(d, 2) for d in delays))
        assert unique_delays > 3, f"Expected variance in delays, got {unique_delays} unique values"
