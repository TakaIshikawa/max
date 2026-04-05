"""Base source adapter interface."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

import httpx

from max.types.signal import Signal

logger = logging.getLogger(__name__)

# Status codes that trigger a retry.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


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

    Returns the successful ``httpx.Response``.
    """
    last_response: httpx.Response | None = None

    for attempt in range(max_retries + 1):
        response = await client.request(method, url, **request_kwargs)
        status = response.status_code

        if status < 400:
            return response

        if status not in _RETRYABLE_STATUS_CODES:
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
    if last_response.status_code == 429:
        raise AdapterRateLimitError(adapter_name, url)
    raise AdapterFetchError(adapter_name, last_response.status_code, url)


class SourceAdapter(ABC):
    """Common interface for all signal sources."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}

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
