"""Base source adapter interface."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

import httpx

from max.types.signal import Signal

logger = logging.getLogger(__name__)

# Status codes that trigger a retry.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, skip calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Circuit breaker to prevent repeated calls to failing adapters.

    Tracks consecutive failures and opens the circuit after a threshold,
    preventing wasted HTTP calls to consistently unavailable services.
    """

    failure_threshold: int = 3
    recovery_timeout: float = 300.0  # 5 minutes
    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = 0
    last_failure_at: float | None = None

    def record_success(self) -> None:
        """Record a successful request, resetting the circuit to CLOSED."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_at = None

    def record_failure(self) -> None:
        """Record a failed request, potentially opening the circuit."""
        self.failure_count += 1
        self.last_failure_at = time.monotonic()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def can_execute(self) -> bool:
        """Check if execution is allowed.

        Returns True if CLOSED, or if OPEN and recovery_timeout has elapsed
        (transitions to HALF_OPEN for testing).
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.HALF_OPEN:
            return True

        # state == OPEN
        if self.last_failure_at is None:
            return True

        elapsed = time.monotonic() - self.last_failure_at
        if elapsed >= self.recovery_timeout:
            self.state = CircuitState.HALF_OPEN
            return True

        return False

    def retry_after(self) -> float:
        """Return seconds until circuit may be retried (for OPEN state)."""
        if self.last_failure_at is None:
            return 0.0
        elapsed = time.monotonic() - self.last_failure_at
        return max(0.0, self.recovery_timeout - elapsed)


@dataclass(frozen=True)
class CircuitBreakerSnapshot:
    """Read-only view of an adapter circuit breaker."""

    adapter_name: str
    state: str
    failure_count: int
    last_failure_at: float | None
    retry_after: float


# Module-level circuit breaker registry keyed by adapter name
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(adapter_name: str) -> CircuitBreaker:
    """Get or create a circuit breaker for the given adapter."""
    if adapter_name not in _circuit_breakers:
        _circuit_breakers[adapter_name] = CircuitBreaker()
    return _circuit_breakers[adapter_name]


def snapshot_circuit_breakers(
    adapter_names: Iterable[str] | None = None,
) -> list[CircuitBreakerSnapshot]:
    """Return circuit breaker state without creating or mutating breakers.

    ``CircuitBreaker.can_execute()`` may transition an open circuit to
    ``HALF_OPEN`` after the recovery timeout. This helper derives the current
    observable state and retry interval without changing the registry.
    """
    now = time.monotonic()
    names = set(adapter_names or ()) | set(_circuit_breakers)
    snapshots: list[CircuitBreakerSnapshot] = []

    for name in sorted(names):
        circuit_breaker = _circuit_breakers.get(name)
        if circuit_breaker is None:
            snapshots.append(
                CircuitBreakerSnapshot(
                    adapter_name=name,
                    state=CircuitState.CLOSED.value,
                    failure_count=0,
                    last_failure_at=None,
                    retry_after=0.0,
                )
            )
            continue

        state = circuit_breaker.state
        retry_after = 0.0
        if circuit_breaker.last_failure_at is not None:
            elapsed = now - circuit_breaker.last_failure_at
            retry_after = max(0.0, circuit_breaker.recovery_timeout - elapsed)
            if state == CircuitState.OPEN and retry_after == 0.0:
                state = CircuitState.HALF_OPEN

        snapshots.append(
            CircuitBreakerSnapshot(
                adapter_name=name,
                state=state.value,
                failure_count=circuit_breaker.failure_count,
                last_failure_at=circuit_breaker.last_failure_at,
                retry_after=retry_after,
            )
        )

    return snapshots


class AdapterFetchError(Exception):
    """Raised when an adapter HTTP request fails with a non-retryable error."""

    def __init__(self, adapter_name: str, status_code: int, url: str) -> None:
        self.adapter_name = adapter_name
        self.status_code = status_code
        self.url = url
        super().__init__(
            f"{adapter_name}: HTTP {status_code} for {url}"
        )


class AdapterRateLimitError(AdapterFetchError):
    """Raised when an adapter receives HTTP 429 after exhausting retries."""

    def __init__(self, adapter_name: str, url: str) -> None:
        super().__init__(adapter_name, 429, url)


class AdapterCircuitOpenError(Exception):
    """Raised when an adapter's circuit breaker is open.

    Indicates the adapter has failed repeatedly and is temporarily disabled
    to prevent wasted HTTP calls.
    """

    def __init__(self, adapter_name: str, retry_after: float) -> None:
        self.adapter_name = adapter_name
        self.retry_after = retry_after
        super().__init__(
            f"{adapter_name}: circuit breaker open, retry in {retry_after:.0f}s"
        )


async def fetch_with_retry(
    url: str,
    client: httpx.AsyncClient,
    *,
    adapter_name: str,
    max_retries: int = 2,
    backoff_base: float = 1.0,
    method: str = "GET",
    **request_kwargs,
) -> httpx.Response:
    """Perform an HTTP request with retry on transient failures.

    Retries on HTTP 429 (rate-limit) and 5xx status codes using exponential
    backoff.  Raises immediately on non-retryable client errors (4xx except 429).

    Uses a circuit breaker to prevent repeated calls to failing adapters.
    After consecutive failures, the circuit opens and blocks requests for a
    recovery period.

    Returns the successful ``httpx.Response``.
    """
    circuit_breaker = get_circuit_breaker(adapter_name)

    # Check circuit breaker before attempting request
    if not circuit_breaker.can_execute():
        retry_after = circuit_breaker.retry_after()
        raise AdapterCircuitOpenError(adapter_name, retry_after)

    last_response: httpx.Response | None = None

    try:
        for attempt in range(max_retries + 1):
            response = await client.request(method, url, **request_kwargs)
            status = response.status_code

            if status < 400:
                circuit_breaker.record_success()
                return response

            if status not in _RETRYABLE_STATUS_CODES:
                circuit_breaker.record_failure()
                raise AdapterFetchError(adapter_name, status, url)

            last_response = response

            if attempt < max_retries:
                delay = backoff_base * (2 ** attempt)
                logger.warning(
                    "%s: HTTP %d from %s — retrying in %.1fs (attempt %d/%d)",
                    adapter_name,
                    status,
                    url,
                    delay,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(delay)

        # All retries exhausted.
        assert last_response is not None
        circuit_breaker.record_failure()
        if last_response.status_code == 429:
            raise AdapterRateLimitError(adapter_name, url)
        raise AdapterFetchError(adapter_name, last_response.status_code, url)

    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        # Network errors, timeouts, etc.
        circuit_breaker.record_failure()
        raise


class SourceAdapter(ABC):
    """Common interface for all signal sources."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}

    def _configured_terms(self, key: str, default: Iterable[str]) -> list[str]:
        """Return a string-list config value plus normalized watchlist terms."""
        configured = self._config.get(key)
        values = list(default) if configured is None else list(configured)
        watchlist_terms = list(self._config.get("watchlist_terms", []))

        seen: set[str] = set()
        terms: list[str] = []
        for value in values + watchlist_terms:
            if not isinstance(value, str):
                continue
            term = value.strip()
            if not term or term in seen:
                continue
            seen.add(term)
            terms.append(term)
        return terms

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique adapter identifier (e.g. 'hackernews', 'npm_registry')."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Signal source type category."""

    @abstractmethod
    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        """Fetch signals from the source. Returns normalized Signal objects."""
