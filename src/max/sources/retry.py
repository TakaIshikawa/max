"""Retry utilities for source adapter network calls with exponential backoff."""

from __future__ import annotations

import asyncio
import logging
import random
from functools import wraps
from typing import Any, Callable, TypeVar, cast

import httpx

from max.sources.errors import (
    SourceAuthError,
    SourceError,
    SourceParseError,
    SourceRateLimitError,
    SourceTransientError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Exception types that should trigger a retry
_RETRYABLE_EXCEPTIONS = (
    SourceRateLimitError,
    SourceTransientError,
    httpx.RequestError,
    httpx.TimeoutException,
)

# Exception types that should NOT trigger a retry (fail fast)
_NON_RETRYABLE_EXCEPTIONS = (
    SourceAuthError,
    SourceParseError,
)


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    adapter_name: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that adds retry logic with exponential backoff and jitter.

    Retries on transient errors (rate limits, network failures, server errors)
    using exponential backoff with jitter. Non-retryable errors (auth, parse)
    are raised immediately.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        adapter_name: Name of the adapter for logging (default: None)

    Returns:
        Decorated function with retry logic

    Example:
        @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_issues")
        async def fetch_data():
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            name = adapter_name or func.__name__

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except _NON_RETRYABLE_EXCEPTIONS:
                    # Auth and parse errors should fail immediately
                    raise
                except _RETRYABLE_EXCEPTIONS as e:
                    last_exception = e

                    # Check if this is the last attempt
                    if attempt >= max_retries:
                        logger.warning(
                            "%s: exhausted retries after %d attempts",
                            name,
                            max_retries + 1,
                            exc_info=True,
                        )
                        raise

                    # Calculate delay with exponential backoff and jitter
                    delay = base_delay * (2**attempt)
                    # Add jitter: random factor between 0.5 and 1.0
                    jitter = random.uniform(0.5, 1.0)
                    actual_delay = delay * jitter

                    # Use retry_after from exception if available
                    if isinstance(e, (SourceRateLimitError, SourceTransientError)):
                        if e.retry_after is not None:
                            actual_delay = e.retry_after

                    logger.warning(
                        "%s: retry attempt %d/%d after %.2fs (error: %s)",
                        name,
                        attempt + 1,
                        max_retries,
                        actual_delay,
                        str(e),
                    )

                    await asyncio.sleep(actual_delay)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"{name}: retry logic failed unexpectedly")

        return wrapper

    return decorator


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    adapter_name: str | None = None,
    **kwargs: Any,
) -> Any:
    """Retry an async function with exponential backoff and jitter.

    This is a functional version of the with_retry decorator for cases where
    you can't use a decorator.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        adapter_name: Name of the adapter for logging (default: None)
        **kwargs: Keyword arguments for func

    Returns:
        Return value of func

    Raises:
        The last exception if all retries are exhausted

    Example:
        result = await retry_async(
            fetch_data,
            url="https://api.example.com",
            max_retries=3,
            base_delay=1.0,
            adapter_name="example",
        )
    """
    last_exception: Exception | None = None
    name = adapter_name or func.__name__

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except _NON_RETRYABLE_EXCEPTIONS:
            # Auth and parse errors should fail immediately
            raise
        except _RETRYABLE_EXCEPTIONS as e:
            last_exception = e

            # Check if this is the last attempt
            if attempt >= max_retries:
                logger.warning(
                    "%s: exhausted retries after %d attempts",
                    name,
                    max_retries + 1,
                    exc_info=True,
                )
                raise

            # Calculate delay with exponential backoff and jitter
            delay = base_delay * (2**attempt)
            # Add jitter: random factor between 0.5 and 1.0
            jitter = random.uniform(0.5, 1.0)
            actual_delay = delay * jitter

            # Use retry_after from exception if available
            if isinstance(e, (SourceRateLimitError, SourceTransientError)):
                if e.retry_after is not None:
                    actual_delay = e.retry_after

            logger.warning(
                "%s: retry attempt %d/%d after %.2fs (error: %s)",
                name,
                attempt + 1,
                max_retries,
                actual_delay,
                str(e),
            )

            await asyncio.sleep(actual_delay)

    # This should never be reached, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError(f"{name}: retry logic failed unexpectedly")
