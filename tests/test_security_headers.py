"""Test security headers and CORS configuration."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app


@pytest.fixture
def client_no_cors():
    """Test client with CORS disabled (default)."""
    with patch.dict("os.environ", {"MAX_CORS_ORIGINS": ""}, clear=False):
        # Force reload of config module to pick up env changes
        import importlib
        import max.config
        importlib.reload(max.config)

        app = create_app()
        yield TestClient(app)


@pytest.fixture
def client_with_cors():
    """Test client with CORS enabled."""
    with patch.dict(
        "os.environ",
        {
            "MAX_CORS_ORIGINS": "http://localhost:3000,https://example.com",
            "MAX_CORS_ALLOW_CREDENTIALS": "true",
        },
        clear=False,
    ):
        # Force reload of config module to pick up env changes
        import importlib
        import max.config
        importlib.reload(max.config)

        app = create_app()
        yield TestClient(app)


def test_security_headers_on_get_response(client_no_cors):
    """Test that security headers are present on GET responses."""
    response = client_no_cors.get("/api/v1/ideas")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    # Cache-Control should NOT be set on GET requests
    assert "Cache-Control" not in response.headers


def test_security_headers_on_post_response(client_no_cors):
    """Test that security headers are present on POST responses."""
    response = client_no_cors.post(
        "/api/v1/signals",
        json={
            "signal_type": "user_feedback",
            "content": "test",
        },
    )

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    # Cache-Control SHOULD be set on POST requests
    assert response.headers["Cache-Control"] == "no-store"


def test_cache_control_on_non_get_methods(client_no_cors):
    """Test that Cache-Control: no-store is set on non-GET methods."""
    for method in ["POST", "PUT", "DELETE"]:
        if method == "POST":
            response = client_no_cors.post(
                "/api/v1/signals",
                json={"signal_type": "test", "content": "test"},
            )
        elif method == "PUT":
            response = client_no_cors.put(
                "/api/v1/ideas/test-id",
                json={"title": "test"},
            )
        else:  # DELETE
            response = client_no_cors.delete("/api/v1/ideas/test-id")

        assert response.headers.get("Cache-Control") == "no-store", f"Failed for {method}"


def test_no_cors_headers_when_disabled(client_no_cors):
    """Test that CORS headers are absent when MAX_CORS_ORIGINS is empty."""
    response = client_no_cors.get("/api/v1/ideas")

    # No CORS headers should be present
    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_cors_headers_when_enabled(client_with_cors):
    """Test that CORS headers appear when MAX_CORS_ORIGINS is set."""
    response = client_with_cors.get(
        "/api/v1/ideas",
        headers={"Origin": "http://localhost:3000"},
    )

    # CORS headers should be present
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"


def test_cors_preflight_request(client_with_cors):
    """Test preflight OPTIONS request returns correct CORS headers."""
    response = client_with_cors.options(
        "/api/v1/ideas",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://example.com"
    assert "POST" in response.headers["Access-Control-Allow-Methods"]
    assert response.headers["Access-Control-Allow-Credentials"] == "true"


def test_cors_rejects_unlisted_origin(client_with_cors):
    """Test that CORS does not allow origins not in the allow list."""
    response = client_with_cors.get(
        "/api/v1/ideas",
        headers={"Origin": "https://evil.com"},
    )

    # FastAPI's CORSMiddleware will not set Access-Control-Allow-Origin
    # for origins not in the allow list
    assert "Access-Control-Allow-Origin" not in response.headers


def test_x_frame_options_deny(client_no_cors):
    """Test that X-Frame-Options: DENY is set on all responses."""
    response = client_no_cors.get("/api/v1/ideas")
    assert response.headers["X-Frame-Options"] == "DENY"

    response = client_no_cors.post(
        "/api/v1/signals",
        json={"signal_type": "test", "content": "test"},
    )
    assert response.headers["X-Frame-Options"] == "DENY"


def test_security_headers_on_mcp_endpoint(client_no_cors):
    """Test that security headers are also present on MCP endpoints."""
    # MCP endpoints should also have security headers
    response = client_no_cors.get("/mcp/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
