"""Focused tests for portfolio evidence concentration REST endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_api_evidence_concentration.db")
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


def _signal(signal_id: str, *, adapter: str, tags: list[str], role: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"API Signal {signal_id}",
        content="Evidence concentration API fixture",
        url=f"https://example.com/api/evidence/{signal_id}",
        tags=tags,
        metadata={"signal_role": role},
    )


def _idea(idea_id: str, *, signals: list[str]) -> BuildableUnit:
    return BuildableUnit(
        id=idea_id,
        title=f"API Idea {idea_id}",
        one_liner="API idea",
        category=BuildableCategory.APPLICATION,
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        evidence_signals=signals,
        status="approved",
        domain="devtools",
    )


def _seed_evidence_concentration(db_path: str) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(_signal("sig-api-1", adapter="forum_a", tags=["devtools"], role="problem"))
        store.insert_signal(_signal("sig-api-2", adapter="forum_a", tags=["devtools"], role="problem"))
        store.insert_signal(_signal("sig-api-3", adapter="registry_b", tags=["ai"], role="solution"))
        store.insert_buildable_unit(_idea("bu-api-1", signals=["sig-api-1", "sig-api-2"]))
        store.insert_buildable_unit(_idea("bu-api-2", signals=["sig-api-3"]))
    finally:
        store.close()


def test_get_portfolio_evidence_concentration_returns_report(client, db_path) -> None:
    _seed_evidence_concentration(db_path)

    response = client.get("/api/v1/portfolio/evidence-concentration", params={"limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "max.evidence_concentration.v1"
    assert payload["limit"] == 1
    assert payload["total_ideas"] == 2
    assert payload["ideas_with_evidence"] == 2
    assert payload["total_evidence_links"] == 3
    assert len(payload["top_concentrated_ideas"]) == 1

    by_adapter = {row["source_adapter"]: row for row in payload["by_source_adapter"]}
    assert by_adapter["forum_a"]["count"] == 2
    assert by_adapter["registry_b"]["count"] == 1
    assert any(row["dimension"] == "source_adapter" for row in payload["recommendations"])


@pytest.mark.parametrize("limit", ["0", "101"])
def test_get_portfolio_evidence_concentration_rejects_invalid_limit(client, limit) -> None:
    response = client.get(
        "/api/v1/portfolio/evidence-concentration",
        params={"limit": limit},
    )

    assert response.status_code == 422


def test_get_portfolio_evidence_concentration_empty_store(client) -> None:
    response = client.get("/api/v1/portfolio/evidence-concentration")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_ideas"] == 0
    assert payload["ideas_with_evidence"] == 0
    assert payload["total_evidence_links"] == 0
    assert payload["by_source_adapter"] == []
    assert payload["by_domain_tag"] == []
    assert payload["by_signal_role"] == []
    assert payload["top_concentrated_ideas"] == []
    assert payload["recommendations"] == []
