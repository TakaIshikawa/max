from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "api_openapi_mcp_candidates.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
    return path


@pytest.fixture
def client(db_path):
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def _signal(
    signal_id: str,
    *,
    adapter: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    credibility: float = 0.7,
    metadata: dict | None = None,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter,
        title=title,
        content=content,
        url=f"https://example.com/{signal_id}",
        tags=tags or [],
        credibility=credibility,
        metadata=metadata or {},
    )


def _seed(db_path: str) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    store.insert_signal(
        _signal(
            "sig-api-linear",
            adapter="apis_guru",
            title="Linear API",
            content="Issue tracking OpenAPI for developer workflow automation and integrations.",
            tags=["productivity"],
            credibility=0.9,
            metadata={
                "provider": "Linear",
                "api_name": "Issues",
                "swagger_url": "https://example.com/linear/openapi.json",
                "openapi_ver": "3.1.0",
                "categories": ["productivity"],
            },
        )
    )
    store.insert_signal(
        _signal(
            "sig-api-linear-demand",
            adapter="github_discussions",
            title="Linear Issues OpenAPI agent integration",
            content="Developers want agent SDK support for issue workflow automation.",
            tags=["linear", "openapi"],
            credibility=0.75,
        )
    )
    store.insert_signal(
        _signal(
            "sig-api-notion",
            adapter="apis_guru",
            title="Notion API",
            content="Workspace API with OpenAPI and integration demand.",
            tags=["productivity"],
            credibility=0.8,
            metadata={
                "provider": "Notion",
                "api_name": "Workspace",
                "swagger_url": "https://example.com/notion/openapi.json",
                "categories": ["productivity"],
            },
        )
    )
    store.insert_signal(
        _signal(
            "sig-api-notion-mcp",
            adapter="mcp_registry",
            title="Notion MCP server",
            content="MCP server for Notion Workspace API.",
            tags=["mcp", "notion"],
            credibility=0.85,
            metadata={"server_name": "notion-mcp"},
        )
    )
    store.close()


def test_get_openapi_mcp_candidates_returns_ranked_candidates(client, db_path) -> None:
    _seed(db_path)

    resp = client.get("/api/v1/mcp/openapi-candidates")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_candidates"] == 2
    assert data["candidates"][0]["provider"] == "Linear"
    assert data["candidates"][0]["rank"] == 1
    assert data["candidates"][0]["existing_mcp_coverage"] is False
    assert data["candidates"][0]["evidence_signal_ids"] == [
        "sig-api-linear",
        "sig-api-linear-demand",
    ]
    assert data["candidates"][0]["source_adapters"] == {
        "apis_guru": 1,
        "github_discussions": 1,
    }
    assert data["candidates"][0]["score_components"]

    by_provider = {candidate["provider"]: candidate for candidate in data["candidates"]}
    assert by_provider["Notion"]["existing_mcp_coverage"] is True
    assert by_provider["Notion"]["coverage_signal_ids"] == ["sig-api-notion-mcp"]
    assert by_provider["Notion"]["score"] < by_provider["Linear"]["score"]


def test_get_openapi_mcp_candidates_filters_and_validates_query_params(client, db_path) -> None:
    _seed(db_path)

    resp = client.get(
        "/api/v1/mcp/openapi-candidates",
        params={"domain": "productivity", "min_score": 70.0},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "productivity"
    assert data["min_score"] == 70.0
    assert [candidate["provider"] for candidate in data["candidates"]] == ["Linear"]

    assert client.get("/api/v1/mcp/openapi-candidates?min_score=-1").status_code == 422
    assert client.get("/api/v1/mcp/openapi-candidates?signal_limit=0").status_code == 422
