"""Tests for source adapter retry utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.errors import (
    SourceAuthError,
    SourceParseError,
    SourceRateLimitError,
    SourceTransientError,
)
from max.sources.retry import retry_async, with_retry


@pytest.fixture
def retry_sleep() -> AsyncMock:
    """Avoid real retry delays while preserving delay assertions."""
    with patch("max.sources.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
        yield sleep


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
    async def test_successful_call_after_transient_failures(self, retry_sleep):
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
        assert [call.args[0] for call in retry_sleep.await_args_list] == [0.01, 0.01]

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises_final_error(self, retry_sleep):
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
        assert retry_sleep.await_count == 2

    @pytest.mark.asyncio
    async def test_backoff_timing_increases_exponentially(self, retry_sleep):
        """Should use exponential backoff with increasing delays."""

        with patch("max.sources.retry.random.uniform", return_value=1.0):
            @with_retry(max_retries=3, base_delay=0.1, adapter_name="test")
            async def fetch_data():
                raise SourceTransientError("Error", adapter_name="test")

            with pytest.raises(SourceTransientError):
                await fetch_data()

        assert [call.args[0] for call in retry_sleep.await_args_list] == [
            0.1,
            0.2,
            0.4,
        ]

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
    async def test_rate_limit_error_uses_retry_after(self, retry_sleep):
        """Should respect retry_after from rate limit errors."""
        call_count = 0

        @with_retry(max_retries=1, base_delay=0.1, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise SourceRateLimitError(
                    "Rate limited", adapter_name="test", retry_after=0.2
                )
            return {"status": "ok"}

        result = await fetch_data()
        assert result == {"status": "ok"}
        assert call_count == 2
        retry_sleep.assert_awaited_once_with(0.2)

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


class TestRetryEdgeCases:
    """Tests for edge cases in retry logic."""

    @pytest.mark.asyncio
    async def test_max_retries_zero_no_retries(self):
        """Should not retry when max_retries=0 (fail immediately after first attempt)."""
        call_count = 0

        @with_retry(max_retries=0, base_delay=0.1, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            raise SourceTransientError("Server error", adapter_name="test")

        with pytest.raises(SourceTransientError, match="Server error"):
            await fetch_data()

        # Should only call once (no retries allowed)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_zero_succeeds_on_first_attempt(self):
        """Should succeed on first attempt even with max_retries=0."""
        call_count = 0

        @with_retry(max_retries=0, base_delay=0.1, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            return {"status": "ok"}

        result = await fetch_data()
        assert result == {"status": "ok"}
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_one_allows_single_retry(self):
        """Should allow exactly one retry when max_retries=1."""
        call_count = 0

        @with_retry(max_retries=1, base_delay=0.05, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise SourceTransientError("Server error", adapter_name="test")
            return {"status": "ok"}

        result = await fetch_data()
        assert result == {"status": "ok"}
        assert call_count == 2  # Initial attempt + 1 retry

    @pytest.mark.asyncio
    async def test_max_retries_one_fails_after_two_attempts(self):
        """Should fail after 2 total attempts when max_retries=1."""
        call_count = 0

        @with_retry(max_retries=1, base_delay=0.05, adapter_name="test")
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            raise SourceTransientError("Persistent error", adapter_name="test")

        with pytest.raises(SourceTransientError, match="Persistent error"):
            await fetch_data()

        assert call_count == 2  # Initial attempt + 1 retry

    @pytest.mark.asyncio
    async def test_retry_async_with_max_retries_zero(self):
        """retry_async should not retry when max_retries=0."""
        call_count = 0

        async def fetch_data():
            nonlocal call_count
            call_count += 1
            raise SourceRateLimitError("Rate limited", adapter_name="test")

        with pytest.raises(SourceRateLimitError):
            await retry_async(
                fetch_data,
                max_retries=0,
                base_delay=0.1,
                adapter_name="test",
            )

        assert call_count == 1


class TestRetryLogging:
    """Tests for retry logging behavior."""

    @pytest.mark.asyncio
    async def test_logs_retry_attempts(self, caplog, retry_sleep):
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
        assert retry_sleep.await_count == 2

    @pytest.mark.asyncio
    async def test_logs_exhausted_retries(self, caplog, retry_sleep):
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
        retry_sleep.assert_awaited_once()


class TestRetryJitter:
    """Tests for retry jitter behavior."""

    @pytest.mark.asyncio
    async def test_jitter_varies_delay(self, retry_sleep):
        """Should apply random jitter to delays (0.5-1.0 multiplier)."""
        jitter_values = [0.5, 0.6, 0.75, 0.9, 1.0]

        for jitter in jitter_values:
            call_count = 0

            @with_retry(max_retries=1, base_delay=1.0, adapter_name="test")
            async def fetch_data():
                nonlocal call_count
                call_count += 1
                raise SourceTransientError("Error", adapter_name="test")

            with patch("max.sources.retry.random.uniform", return_value=jitter):
                with pytest.raises(SourceTransientError):
                    await fetch_data()
            assert call_count == 2

        delays = [call.args[0] for call in retry_sleep.await_args_list]
        assert delays == jitter_values

        # Delays should vary (not all the same)
        assert len(set(delays)) > 3
