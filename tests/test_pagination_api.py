"""Integration tests for pagination API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store


@pytest.fixture
def db_path(tmp_path):
    """Create a temp DB path and initialize schema."""
    path = str(tmp_path / "test_pagination_api.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
    return path


@pytest.fixture
def client(db_path):
    """TestClient with get_store overridden to use per-request connections."""
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store

    with TestClient(app) as c:
        yield c


def test_signals_pagination_api(client):
    """Test GET /api/v1/signals with cursor pagination."""
    # Create 5 signals
    for i in range(5):
        client.post(
            "/api/v1/signals",
            json={
                "title": f"Signal {i}",
                "content": f"Content {i}",
                "url": f"https://example.com/{i}",
            },
        )

    # Get first page with limit 2
    resp = client.get("/api/v1/signals?limit=2")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["items"]) == 2
    assert data["pagination"]["has_more"] is True
    assert data["pagination"]["next_cursor"] is not None
    assert data["pagination"]["total_count"] == 5

    # Get second page using cursor
    cursor = data["pagination"]["next_cursor"]
    resp2 = client.get(f"/api/v1/signals?limit=2&cursor={cursor}")
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert len(data2["items"]) == 2
    assert data2["pagination"]["has_more"] is True
    assert data2["pagination"]["total_count"] == 5

    # Verify no overlap
    page1_ids = {item["id"] for item in data["items"]}
    page2_ids = {item["id"] for item in data2["items"]}
    assert page1_ids.isdisjoint(page2_ids)

    # Get last page
    cursor2 = data2["pagination"]["next_cursor"]
    resp3 = client.get(f"/api/v1/signals?limit=2&cursor={cursor2}")
    assert resp3.status_code == 200
    data3 = resp3.json()

    assert len(data3["items"]) == 1
    assert data3["pagination"]["has_more"] is False
    assert data3["pagination"]["next_cursor"] is None


def test_insights_pagination_api(client):
    """Test GET /api/v1/insights with cursor pagination."""
    # Create 3 insights
    for i in range(3):
        client.post(
            "/api/v1/insights",
            json={
                "title": f"Insight {i}",
                "summary": f"Summary {i}",
            },
        )

    # Get first page
    resp = client.get("/api/v1/insights?limit=2")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["items"]) == 2
    assert data["pagination"]["has_more"] is True
    assert data["pagination"]["total_count"] == 3

    # Get second page
    cursor = data["pagination"]["next_cursor"]
    resp2 = client.get(f"/api/v1/insights?limit=2&cursor={cursor}")
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert len(data2["items"]) == 1
    assert data2["pagination"]["has_more"] is False


def test_ideas_pagination_api(client):
    """Test GET /api/v1/ideas with cursor pagination."""
    # Create 4 ideas
    for i in range(4):
        client.post(
            "/api/v1/ideas",
            json={
                "title": f"Idea {i}",
                "one_liner": f"One liner {i}",
                "problem": f"Problem {i}",
                "solution": f"Solution {i}",
                "value_proposition": f"Value {i}",
            },
        )

    # Get first page
    resp = client.get("/api/v1/ideas?limit=2")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["items"]) == 2
    assert data["pagination"]["has_more"] is True
    assert data["pagination"]["total_count"] == 4

    # Get second page
    cursor = data["pagination"]["next_cursor"]
    resp2 = client.get(f"/api/v1/ideas?limit=2&cursor={cursor}")
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert len(data2["items"]) == 2
    assert data2["pagination"]["has_more"] is False


def test_pagination_with_filters(client):
    """Test pagination works with query filters."""
    # Create signals with different source types
    for i in range(3):
        client.post(
            "/api/v1/signals",
            json={
                "title": f"Forum {i}",
                "content": f"Content {i}",
                "url": f"https://example.com/forum/{i}",
                "source_type": "forum",
            },
        )
    for i in range(2):
        client.post(
            "/api/v1/signals",
            json={
                "title": f"Registry {i}",
                "content": f"Content {i}",
                "url": f"https://example.com/registry/{i}",
                "source_type": "registry",
            },
        )

    # Get only forum signals
    resp = client.get("/api/v1/signals?source_type=forum")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["items"]) == 3
    assert data["pagination"]["total_count"] == 3
    assert all(item["source_type"] == "forum" for item in data["items"])


def test_pagination_response_schema(client):
    """Verify paginated response has correct schema."""
    resp = client.get("/api/v1/signals")
    assert resp.status_code == 200
    data = resp.json()

    # Check top-level structure
    assert "items" in data
    assert "pagination" in data

    # Check pagination metadata
    pagination = data["pagination"]
    assert "next_cursor" in pagination
    assert "has_more" in pagination
    assert "total_count" in pagination

    assert isinstance(pagination["has_more"], bool)
    assert isinstance(pagination["total_count"], int)
    assert pagination["next_cursor"] is None or isinstance(pagination["next_cursor"], str)


def test_limit_clamping_api(client):
    """Test that limit is clamped to max 100."""
    # Create 10 signals
    for i in range(10):
        client.post(
            "/api/v1/signals",
            json={
                "title": f"Signal {i}",
                "content": f"Content {i}",
                "url": f"https://example.com/{i}",
            },
        )

    # Request with limit > 100
    resp = client.get("/api/v1/signals?limit=150")
    assert resp.status_code == 200
    data = resp.json()

    # Should return all 10 items (clamped to 100, but only 10 exist)
    assert len(data["items"]) == 10
    assert data["pagination"]["has_more"] is False


def test_invalid_cursor(client):
    """Test that invalid cursor is handled gracefully."""
    resp = client.get("/api/v1/signals?cursor=invalid_cursor_123")
    # Should return 400 Bad Request for invalid cursor
    assert resp.status_code == 400
    assert "cursor" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()
