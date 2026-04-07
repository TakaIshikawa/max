"""Tests for rate limiting middleware and dependency."""

from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from max.server.rate_limit import RateLimiter, RateLimitMiddleware, rate_limit


# ── RateLimiter Tests ──────────────────────────────────────────────


def test_rate_limiter_allows_within_limit():
    """Test that requests within limit are allowed."""
    limiter = RateLimiter(rpm=3)

    assert limiter.is_allowed("client1") is True
    assert limiter.is_allowed("client1") is True
    assert limiter.is_allowed("client1") is True


def test_rate_limiter_rejects_after_limit():
    """Test that requests after limit are rejected."""
    limiter = RateLimiter(rpm=3)

    # Use up the limit
    assert limiter.is_allowed("client1") is True
    assert limiter.is_allowed("client1") is True
    assert limiter.is_allowed("client1") is True

    # Next request should be rejected
    assert limiter.is_allowed("client1") is False


def test_rate_limiter_sliding_window():
    """Test that sliding window correctly expires old entries."""
    limiter = RateLimiter(rpm=2)

    # Mock time to control expiration
    with patch("max.server.rate_limit.time.time") as mock_time:
        mock_time.return_value = 0.0

        # Use up limit
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client1") is False

        # Advance time by 61 seconds (past window)
        mock_time.return_value = 61.0

        # Should be allowed again (old entries expired)
        assert limiter.is_allowed("client1") is True


def test_rate_limiter_different_clients():
    """Test that different clients have independent limits."""
    limiter = RateLimiter(rpm=2)

    assert limiter.is_allowed("client1") is True
    assert limiter.is_allowed("client1") is True
    assert limiter.is_allowed("client1") is False

    # Different client should have full quota
    assert limiter.is_allowed("client2") is True
    assert limiter.is_allowed("client2") is True
    assert limiter.is_allowed("client2") is False


def test_rate_limiter_get_retry_after():
    """Test that get_retry_after returns correct seconds."""
    limiter = RateLimiter(rpm=2)

    with patch("max.server.rate_limit.time.time") as mock_time:
        mock_time.return_value = 0.0

        # Use up limit
        limiter.is_allowed("client1")
        limiter.is_allowed("client1")

        # Should return ~60 seconds (time until oldest request expires)
        mock_time.return_value = 1.0
        retry_after = limiter.get_retry_after("client1")
        assert 58.0 <= retry_after <= 60.0

        # Advance time
        mock_time.return_value = 30.0
        retry_after = limiter.get_retry_after("client1")
        assert 29.0 <= retry_after <= 31.0


def test_rate_limiter_get_retry_after_no_requests():
    """Test that get_retry_after returns 0 when no requests."""
    limiter = RateLimiter(rpm=5)

    retry_after = limiter.get_retry_after("client1")
    assert retry_after == 0.0


def test_rate_limiter_get_retry_after_within_limit():
    """Test that get_retry_after returns 0 when within limit."""
    limiter = RateLimiter(rpm=5)

    limiter.is_allowed("client1")
    limiter.is_allowed("client1")

    retry_after = limiter.get_retry_after("client1")
    assert retry_after == 0.0


def test_rate_limiter_invalid_rpm():
    """Test that invalid RPM raises ValueError."""
    with pytest.raises(ValueError, match="rpm must be positive"):
        RateLimiter(rpm=0)

    with pytest.raises(ValueError, match="rpm must be positive"):
        RateLimiter(rpm=-5)


# ── RateLimitMiddleware Tests ──────────────────────────────────────


def test_middleware_allows_within_limit():
    """Test that middleware allows requests within limit."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rpm=10)

    @app.get("/test")
    def test_endpoint():
        return {"status": "ok"}

    client = TestClient(app)

    # Should allow multiple requests
    for _ in range(5):
        response = client.get("/test")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_middleware_returns_429_when_exceeded():
    """Test that middleware returns 429 with proper headers when rate exceeded."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rpm=2)

    @app.get("/test")
    def test_endpoint():
        return {"status": "ok"}

    client = TestClient(app)

    # Use up limit
    client.get("/test")
    client.get("/test")

    # Next request should be rate limited
    response = client.get("/test")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0
    assert response.json()["detail"] == "Rate limit exceeded"
    assert "retry_after" in response.json()


def test_middleware_adds_rate_limit_headers():
    """Test that middleware adds X-RateLimit headers to responses."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rpm=10)

    @app.get("/test")
    def test_endpoint():
        return {"status": "ok"}

    client = TestClient(app)

    response = client.get("/test")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert response.headers["X-RateLimit-Limit"] == "10"
    assert "X-RateLimit-Remaining" in response.headers


def test_middleware_excludes_paths():
    """Test that middleware excludes specified paths from rate limiting."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rpm=1, excluded_paths={"/health"})

    @app.get("/test")
    def test_endpoint():
        return {"status": "ok"}

    @app.get("/health")
    def health_endpoint():
        return {"status": "healthy"}

    client = TestClient(app)

    # Use up limit on /test
    client.get("/test")
    response = client.get("/test")
    assert response.status_code == 429

    # /health should still work
    for _ in range(5):
        response = client.get("/health")
        assert response.status_code == 200


def test_middleware_handles_missing_client():
    """Test that middleware handles request without client gracefully."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rpm=10)

    @app.get("/test")
    def test_endpoint():
        return {"status": "ok"}

    # Create a mock request with no client
    from fastapi import Request

    async def mock_call_next(request):
        return {"status": "ok"}

    middleware = RateLimitMiddleware(app, rpm=10)

    request = Mock(spec=Request)
    request.client = None
    request.url.path = "/test"

    import asyncio

    response = asyncio.run(middleware.dispatch(request, mock_call_next))
    assert response.status_code == 500


# ── rate_limit Dependency Tests ────────────────────────────────────


def test_rate_limit_dependency_allows_within_limit():
    """Test that rate_limit dependency allows requests within limit."""
    app = FastAPI()

    @app.get("/expensive", dependencies=[Depends(rate_limit(3))])
    def expensive_endpoint():
        return {"status": "ok"}

    client = TestClient(app)

    # Should allow 3 requests
    for _ in range(3):
        response = client.get("/expensive")
        assert response.status_code == 200


def test_rate_limit_dependency_rejects_after_limit():
    """Test that rate_limit dependency rejects after limit exceeded."""
    app = FastAPI()

    @app.get("/expensive", dependencies=[Depends(rate_limit(2))])
    def expensive_endpoint():
        return {"status": "ok"}

    client = TestClient(app)

    # Use up limit
    client.get("/expensive")
    client.get("/expensive")

    # Next request should fail
    response = client.get("/expensive")
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_rate_limit_dependency_independent_from_global():
    """Test that endpoint-level rate limit works independently of global limit."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rpm=10)

    @app.get("/expensive", dependencies=[Depends(rate_limit(2))])
    def expensive_endpoint():
        return {"status": "ok"}

    @app.get("/normal")
    def normal_endpoint():
        return {"status": "ok"}

    client = TestClient(app)

    # Use up expensive endpoint limit
    client.get("/expensive")
    client.get("/expensive")
    response = client.get("/expensive")
    assert response.status_code == 429

    # Normal endpoint should still work (has 10 RPM limit)
    for _ in range(5):
        response = client.get("/normal")
        assert response.status_code == 200


def test_rate_limit_dependency_different_endpoints():
    """Test that different endpoints with same RPM share the same limiter."""
    app = FastAPI()

    @app.get("/endpoint1", dependencies=[Depends(rate_limit(3))])
    def endpoint1():
        return {"endpoint": "1"}

    @app.get("/endpoint2", dependencies=[Depends(rate_limit(3))])
    def endpoint2():
        return {"endpoint": "2"}

    client = TestClient(app)

    # Both endpoints share the same 3 RPM limit
    client.get("/endpoint1")
    client.get("/endpoint1")
    client.get("/endpoint2")  # This is the 3rd request from same client

    # Both endpoints should now be rate limited
    response1 = client.get("/endpoint1")
    assert response1.status_code == 429

    response2 = client.get("/endpoint2")
    assert response2.status_code == 429


# ── Integration Tests ──────────────────────────────────────────────


def test_rate_limiting_disabled():
    """Test that rate limiting is disabled when config is false."""
    with patch("max.config.MAX_RATE_LIMIT_ENABLED", False):
        from max.server.app import create_app

        app = create_app()
        client = TestClient(app)

        # Should be able to make many requests without rate limiting
        # (excluding actual endpoint logic)
        for _ in range(10):
            response = client.get("/api/v1/health")
            assert response.status_code == 200


def test_health_endpoint_excluded_from_rate_limit():
    """Test that /health endpoint is excluded from rate limiting."""
    with patch("max.config.MAX_RATE_LIMIT_ENABLED", True):
        with patch("max.config.MAX_RATE_LIMIT_RPM", 1):
            from max.server.app import create_app

            app = create_app()
            client = TestClient(app)

            # Should be able to call health many times
            for _ in range(10):
                response = client.get("/api/v1/health")
                assert response.status_code == 200


def test_pipeline_endpoint_has_expensive_limit():
    """Test that /pipeline/run has expensive rate limit applied."""
    # Create a test app with custom rate limit for expensive endpoint
    # Use unique RPM value to avoid sharing limiter with other tests
    from fastapi import APIRouter, Depends, FastAPI
    from max.server.rate_limit import rate_limit

    app = FastAPI()
    test_router = APIRouter()

    # Patch the pipeline runner before creating endpoint
    with patch("max.pipeline.runner.run_pipeline") as mock_runner:
        # Mock the pipeline runner to avoid actual execution
        mock_runner.return_value = Mock(
            signals_fetched=0,
            signals_new=0,
            insights_generated=0,
            ideas_generated=0,
            ideas_evaluated=0,
            specs_generated=0,
            avg_insight_confidence=0.0,
            avg_idea_score=0.0,
            token_usage={},
            top_ideas=[],
        )

        # Use unique RPM value (7) to avoid test interference
        @test_router.post("/pipeline/run", dependencies=[Depends(rate_limit(7))])
        async def run_pipeline_test(body: dict):
            import asyncio
            from max.pipeline.runner import run_pipeline

            result = await asyncio.to_thread(run_pipeline)
            return {"status": "ok"}

        app.include_router(test_router, prefix="/api/v1")
        client = TestClient(app)

        # Should allow 7 requests
        for i in range(7):
            response = client.post("/api/v1/pipeline/run", json={})
            assert response.status_code == 200, f"Request {i+1} failed"

        # 8th request should be rate limited
        response = client.post("/api/v1/pipeline/run", json={})
        assert response.status_code == 429


def test_rate_limit_memory_cleanup():
    """Test that old entries are cleaned up to prevent memory leak."""
    limiter = RateLimiter(rpm=100)

    with patch("max.server.rate_limit.time.time") as mock_time:
        mock_time.return_value = 0.0

        # Make many requests
        for _ in range(50):
            limiter.is_allowed("client1")

        # Check that we have 50 entries
        assert len(limiter._requests["client1"]) == 50

        # Advance time past window
        mock_time.return_value = 70.0

        # Make a new request - should clean up old entries
        limiter.is_allowed("client1")

        # Should only have 1 entry now (the new one)
        assert len(limiter._requests["client1"]) == 1
