"""Tests for circuit breaker functionality in source adapters."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import (
    AdapterCircuitOpenError,
    AdapterFetchError,
    CircuitBreaker,
    CircuitState,
    fetch_with_retry,
    get_circuit_breaker,
    snapshot_circuit_breakers,
)


def _mock_response(status_code: int) -> httpx.Response:
    """Create a minimal httpx.Response with the given status code."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    return resp


def _mock_client(*status_codes: int) -> httpx.AsyncClient:
    """Return a mock AsyncClient whose .request() yields responses in order."""
    responses = [_mock_response(code) for code in status_codes]
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=responses)
    return client


# ── CircuitBreaker unit tests ───────────────────────────────────────


class TestCircuitBreakerStates:
    """Test circuit breaker state machine."""

    def test_initial_state_is_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.last_failure_at is None

    def test_closed_allows_execution(self) -> None:
        cb = CircuitBreaker()
        assert cb.can_execute() is True

    def test_record_failure_increments_count(self) -> None:
        cb = CircuitBreaker()
        cb.record_failure()
        assert cb.failure_count == 1
        assert cb.state == CircuitState.CLOSED  # Still closed (threshold is 3)

    def test_failure_threshold_opens_circuit(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    def test_open_state_blocks_execution(self) -> None:
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_record_success_resets_to_closed(self) -> None:
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.last_failure_at is None

    def test_open_transitions_to_half_open_after_timeout(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

        # After timeout elapses, can_execute() transitions to HALF_OPEN
        time.sleep(0.15)
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_allows_execution(self) -> None:
        cb = CircuitBreaker()
        cb.state = CircuitState.HALF_OPEN
        assert cb.can_execute() is True

    def test_half_open_success_resets_to_closed(self) -> None:
        cb = CircuitBreaker()
        cb.state = CircuitState.HALF_OPEN
        cb.failure_count = 5
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_failure_reopens_circuit(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        cb.state = CircuitState.HALF_OPEN
        cb.failure_count = 2  # Already had 2 failures before
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    def test_retry_after_returns_remaining_timeout(self) -> None:
        cb = CircuitBreaker(recovery_timeout=10.0)
        cb.record_failure()
        retry_after = cb.retry_after()
        assert 9.0 < retry_after <= 10.0

    def test_retry_after_zero_when_no_failure(self) -> None:
        cb = CircuitBreaker()
        assert cb.retry_after() == 0.0


class TestGetCircuitBreaker:
    """Test circuit breaker registry."""

    def test_creates_new_circuit_breaker(self) -> None:
        cb = get_circuit_breaker("test_adapter")
        assert isinstance(cb, CircuitBreaker)
        assert cb.state == CircuitState.CLOSED

    def test_returns_same_instance_for_same_name(self) -> None:
        cb1 = get_circuit_breaker("test_adapter_2")
        cb2 = get_circuit_breaker("test_adapter_2")
        assert cb1 is cb2

    def test_different_instances_for_different_names(self) -> None:
        cb1 = get_circuit_breaker("adapter_a")
        cb2 = get_circuit_breaker("adapter_b")
        assert cb1 is not cb2


class TestSnapshotCircuitBreakers:
    """Test non-mutating circuit breaker snapshots."""

    def test_includes_known_adapters_without_creating_breakers(self) -> None:
        adapter_name = f"known_adapter_{time.monotonic()}"

        snapshots = snapshot_circuit_breakers(adapter_names=[adapter_name])

        snap = next(s for s in snapshots if s.adapter_name == adapter_name)
        assert snap.state == "closed"
        assert snap.failure_count == 0
        assert snap.last_failure_at is None
        assert snap.retry_after == 0.0

    def test_includes_registry_adapters_not_in_known_list(self) -> None:
        adapter_name = f"registry_only_{time.monotonic()}"
        cb = get_circuit_breaker(adapter_name)
        cb.record_failure()

        snapshots = snapshot_circuit_breakers(adapter_names=["known_only"])

        names = {s.adapter_name for s in snapshots}
        assert "known_only" in names
        assert adapter_name in names

    def test_expired_open_circuit_reports_half_open_without_mutating(self) -> None:
        adapter_name = f"expired_open_{time.monotonic()}"
        cb = get_circuit_breaker(adapter_name)
        cb.failure_threshold = 1
        cb.recovery_timeout = 0.1
        cb.record_failure()

        time.sleep(0.15)
        snapshots = snapshot_circuit_breakers(adapter_names=[adapter_name])

        snap = next(s for s in snapshots if s.adapter_name == adapter_name)
        assert snap.state == "half_open"
        assert snap.retry_after == 0.0
        assert cb.state == CircuitState.OPEN


# ── AdapterCircuitOpenError ──────────────────────────────────────────


class TestAdapterCircuitOpenError:
    def test_attributes(self) -> None:
        err = AdapterCircuitOpenError("reddit", 300.0)
        assert err.adapter_name == "reddit"
        assert err.retry_after == 300.0
        assert "reddit" in str(err)
        assert "300s" in str(err)

    def test_is_exception(self) -> None:
        assert issubclass(AdapterCircuitOpenError, Exception)


# ── Integration with fetch_with_retry ────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_success_records_success_on_circuit_breaker() -> None:
    """Successful fetch should reset the circuit breaker."""
    # Clear any existing state
    cb = get_circuit_breaker("test_success_cb")
    cb.record_failure()
    cb.record_failure()
    assert cb.failure_count == 2

    client = _mock_client(200)
    with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
        await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name="test_success_cb",
        )

    # Circuit breaker should be reset
    cb = get_circuit_breaker("test_success_cb")
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_fetch_failure_records_failure_on_circuit_breaker() -> None:
    """Failed fetch should record failure on circuit breaker."""
    # Create fresh circuit breaker
    adapter_name = f"test_failure_cb_{time.monotonic()}"
    cb = get_circuit_breaker(adapter_name)
    assert cb.failure_count == 0

    client = _mock_client(404)
    with pytest.raises(AdapterFetchError):
        await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name=adapter_name,
        )

    cb = get_circuit_breaker(adapter_name)
    assert cb.failure_count == 1


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_failures() -> None:
    """Circuit should open after consecutive failures reach threshold."""
    adapter_name = f"test_open_circuit_{time.monotonic()}"

    # Make 3 consecutive failures
    for i in range(3):
        client = _mock_client(500, 500, 500)  # Exhausts retries
        with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(AdapterFetchError):
                await fetch_with_retry(
                    "https://example.com/api",
                    client,
                    adapter_name=adapter_name,
                    max_retries=2,
                )

    # Circuit should be open
    cb = get_circuit_breaker(adapter_name)
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 3


@pytest.mark.asyncio
async def test_open_circuit_blocks_execution_immediately() -> None:
    """When circuit is open, fetch_with_retry should raise immediately without HTTP calls."""
    adapter_name = f"test_blocked_{time.monotonic()}"

    # Open the circuit
    for i in range(3):
        client = _mock_client(500, 500, 500)
        with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(AdapterFetchError):
                await fetch_with_retry(
                    "https://example.com/api",
                    client,
                    adapter_name=adapter_name,
                    max_retries=2,
                )

    # Attempt another request — should be blocked without making HTTP call
    client = _mock_client(200)  # This should never be called
    with pytest.raises(AdapterCircuitOpenError) as exc_info:
        await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name=adapter_name,
        )

    assert exc_info.value.adapter_name == adapter_name
    assert exc_info.value.retry_after > 0
    # Verify no HTTP call was made
    client.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_half_open_success_closes_circuit() -> None:
    """After recovery timeout, successful request should close the circuit."""
    adapter_name = f"test_half_open_success_{time.monotonic()}"
    cb = get_circuit_breaker(adapter_name)
    cb.failure_threshold = 2
    cb.recovery_timeout = 0.1

    # Open circuit with 2 failures
    for i in range(2):
        client = _mock_client(503, 503, 503)
        with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(AdapterFetchError):
                await fetch_with_retry(
                    "https://example.com/api",
                    client,
                    adapter_name=adapter_name,
                    max_retries=2,
                )

    assert cb.state == CircuitState.OPEN

    # Wait for recovery timeout
    time.sleep(0.15)

    # Successful request should transition OPEN → HALF_OPEN → CLOSED
    client = _mock_client(200)
    with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
        await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name=adapter_name,
        )

    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_half_open_failure_reopens_circuit() -> None:
    """After recovery timeout, failed request should reopen the circuit."""
    adapter_name = f"test_half_open_fail_{time.monotonic()}"
    cb = get_circuit_breaker(adapter_name)
    cb.failure_threshold = 2
    cb.recovery_timeout = 0.1

    # Open circuit
    for i in range(2):
        client = _mock_client(500, 500, 500)
        with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(AdapterFetchError):
                await fetch_with_retry(
                    "https://example.com/api",
                    client,
                    adapter_name=adapter_name,
                    max_retries=2,
                )

    assert cb.state == CircuitState.OPEN

    # Wait for recovery timeout
    time.sleep(0.15)

    # Failed request should keep circuit open
    client = _mock_client(503, 503, 503)
    with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(AdapterFetchError):
            await fetch_with_retry(
                "https://example.com/api",
                client,
                adapter_name=adapter_name,
                max_retries=2,
            )

    assert cb.state == CircuitState.OPEN
    assert cb.failure_count >= cb.failure_threshold


@pytest.mark.asyncio
async def test_network_error_records_failure() -> None:
    """Network errors should also record circuit breaker failure."""
    adapter_name = f"test_network_error_{time.monotonic()}"
    cb = get_circuit_breaker(adapter_name)

    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with pytest.raises(httpx.ConnectError):
        await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name=adapter_name,
        )

    assert cb.failure_count == 1


# ── Pipeline integration tests ───────────────────────────────────────


def test_pipeline_skips_open_circuit_adapter() -> None:
    """Pipeline should skip adapters with open circuits and log appropriately."""
    from max.pipeline.runner import _fetch_all_signals
    from max.sources.base import SourceAdapter
    from max.types.signal import Signal

    # Create a mock adapter with open circuit
    adapter_name = f"test_pipeline_skip_{time.monotonic()}"

    class FailingAdapter(SourceAdapter):
        @property
        def name(self) -> str:
            return adapter_name

        @property
        def source_type(self) -> str:
            return "test"

        async def fetch(self, *, limit: int = 30) -> list[Signal]:
            # This will trigger circuit breaker via fetch_with_retry
            client = _mock_client(500, 500, 500)
            with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
                await fetch_with_retry(
                    "https://example.com/api",
                    client,
                    adapter_name=self.name,
                    max_retries=2,
                )
            return []

    # Open the circuit by failing 3 times
    adapter = FailingAdapter()
    for i in range(3):
        try:
            import asyncio
            asyncio.run(adapter.fetch(limit=5))
        except AdapterFetchError:
            pass

    cb = get_circuit_breaker(adapter_name)
    assert cb.state == CircuitState.OPEN

    # Now attempt to fetch in pipeline context
    # Mock get_all_adapters to return our failing adapter
    with patch("max.pipeline.runner.get_all_adapters", return_value=[adapter]):
        signals, allocation, metrics = _fetch_all_signals(signal_limit=10)

    # Verify adapter was skipped due to circuit breaker
    assert metrics[adapter_name]["status"] == "circuit_open"
    assert metrics[adapter_name]["signal_count"] == 0
    assert "circuit breaker open" in metrics[adapter_name]["error_message"]
    assert len(signals) == 0


def test_pipeline_logs_circuit_open_at_info_level(caplog) -> None:
    """Pipeline should log circuit-open events at INFO level, not WARNING."""
    import asyncio
    import logging

    from max.pipeline.runner import _fetch_all_signals
    from max.sources.base import SourceAdapter
    from max.types.signal import Signal

    adapter_name = f"test_log_level_{time.monotonic()}"

    class CircuitOpenAdapter(SourceAdapter):
        @property
        def name(self) -> str:
            return adapter_name

        @property
        def source_type(self) -> str:
            return "test"

        async def fetch(self, *, limit: int = 30) -> list[Signal]:
            cb = get_circuit_breaker(self.name)
            cb.state = CircuitState.OPEN
            cb.last_failure_at = time.monotonic()
            cb.failure_count = 3

            # This will immediately raise AdapterCircuitOpenError
            client = _mock_client(200)
            await fetch_with_retry(
                "https://example.com/api",
                client,
                adapter_name=self.name,
            )
            return []

    adapter = CircuitOpenAdapter()

    with caplog.at_level(logging.INFO, logger="max.pipeline.runner"):
        with patch("max.pipeline.runner.get_all_adapters", return_value=[adapter]):
            _fetch_all_signals(signal_limit=10)

    # Verify INFO level log
    assert any(
        adapter_name in msg and "circuit breaker open" in msg
        for msg in caplog.messages
    )
    # Should be logged at INFO, not WARNING
    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any(adapter_name in r.message for r in info_records)
