"""Rate limiting middleware and dependency for FastAPI."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimiter:
    """Token-bucket rate limiter using sliding window approach.

    Tracks request timestamps per client key (typically IP address).
    Prunes old entries on each check to prevent memory leaks.

    Note: In-memory implementation - not suitable for multi-process deployments.
    """

    def __init__(self, rpm: int):
        """Initialize rate limiter.

        Args:
            rpm: Requests per minute allowed per client.
        """
        if rpm <= 0:
            raise ValueError(f"rpm must be positive, got {rpm}")

        self.rpm = rpm
        self.window_seconds = 60.0
        # Dict[client_key, List[timestamp]]
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if a request from the given key is allowed.

        Prunes expired entries and checks if count is within limit.

        Args:
            key: Client identifier (typically IP address).

        Returns:
            True if request is allowed, False if rate limit exceeded.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Prune old entries
        self._requests[key] = [ts for ts in self._requests[key] if ts > cutoff]

        # Check limit
        if len(self._requests[key]) >= self.rpm:
            return False

        # Record this request
        self._requests[key].append(now)
        return True

    def get_retry_after(self, key: str) -> float:
        """Get seconds until next request will be allowed.

        Args:
            key: Client identifier.

        Returns:
            Seconds until rate limit window resets for oldest request.
            Returns 0.0 if no requests or all expired.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Get valid requests in window
        valid_requests = [ts for ts in self._requests.get(key, []) if ts > cutoff]

        if not valid_requests or len(valid_requests) < self.rpm:
            return 0.0

        # Time until oldest request expires from window
        oldest = min(valid_requests)
        retry_after = (oldest + self.window_seconds) - now
        return max(0.0, retry_after)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global rate limiting middleware.

    Applies rate limit to all requests except excluded paths.
    Returns 429 with Retry-After header when limit exceeded.
    """

    def __init__(self, app, rpm: int, excluded_paths: set[str] | None = None):
        """Initialize middleware.

        Args:
            app: FastAPI application.
            rpm: Requests per minute per client.
            excluded_paths: Set of path prefixes to exclude (e.g. {"/health"}).
        """
        super().__init__(app)
        self.limiter = RateLimiter(rpm)
        self.excluded_paths = excluded_paths or set()

    async def dispatch(self, request: Request, call_next: Callable):
        """Process request with rate limiting."""
        # Skip excluded paths
        for excluded in self.excluded_paths:
            if request.url.path.startswith(excluded):
                return await call_next(request)

        # Get client identifier
        if request.client is None:
            # Should not happen in normal operation
            return JSONResponse(
                status_code=500,
                content={"detail": "Unable to identify client"},
            )

        client_key = request.client.host

        # Check rate limit
        if not self.limiter.is_allowed(client_key):
            retry_after = self.limiter.get_retry_after(client_key)
            return JSONResponse(
                status_code=429,
                headers={
                    "Retry-After": str(int(retry_after) + 1),  # Round up
                    "X-RateLimit-Limit": str(self.limiter.rpm),
                    "X-RateLimit-Remaining": "0",
                },
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
            )

        # Add rate limit headers to response
        response = await call_next(request)

        # Calculate remaining requests
        now = time.time()
        cutoff = now - self.limiter.window_seconds
        valid_requests = [
            ts for ts in self.limiter._requests.get(client_key, [])
            if ts > cutoff
        ]
        remaining = max(0, self.limiter.rpm - len(valid_requests))

        response.headers["X-RateLimit-Limit"] = str(self.limiter.rpm)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


# Global limiter instances for dependency injection
_endpoint_limiters: dict[int, RateLimiter] = {}


def _get_limiter(rpm: int) -> RateLimiter:
    """Get or create a RateLimiter for the given RPM."""
    if rpm not in _endpoint_limiters:
        _endpoint_limiters[rpm] = RateLimiter(rpm)
    return _endpoint_limiters[rpm]


def rate_limit(rpm: int):
    """FastAPI dependency for endpoint-specific rate limiting.

    Usage:
        @router.post("/expensive", dependencies=[Depends(rate_limit(5))])
        def expensive_endpoint():
            ...

    Args:
        rpm: Requests per minute allowed for this endpoint.

    Returns:
        Dependency function that raises HTTPException(429) if limit exceeded.
    """
    limiter = _get_limiter(rpm)

    async def check_rate_limit(request: Request):
        """Check rate limit for this request."""
        if request.client is None:
            raise HTTPException(
                status_code=500,
                detail="Unable to identify client",
            )

        client_key = request.client.host

        if not limiter.is_allowed(client_key):
            retry_after = limiter.get_retry_after(client_key)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(int(retry_after) + 1),
                    "X-RateLimit-Limit": str(rpm),
                    "X-RateLimit-Remaining": "0",
                },
            )

        # Return remaining count for informational headers
        now = time.time()
        cutoff = now - limiter.window_seconds
        valid_requests = [
            ts for ts in limiter._requests.get(client_key, [])
            if ts > cutoff
        ]
        remaining = max(0, limiter.rpm - len(valid_requests))

        # Store in request state for middleware to add headers
        request.state.rate_limit_info = {
            "limit": rpm,
            "remaining": remaining,
        }

    return check_rate_limit
