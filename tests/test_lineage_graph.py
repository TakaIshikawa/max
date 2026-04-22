"""Tests for idea lineage graph REST responses."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def lineage_client(tmp_path):
    from max.server.dependencies import get_store

    db_path = str(tmp_path / "lineage.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    app = create_app()

    def override_get_store():
        request_store = Store(db_path=db_path, wal_mode=True)
        try:
            yield request_store
        finally:
            request_store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), db_path


def _seed_lineage(db_path: str) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-lineage-problem",
                source_type=SignalSourceType.FORUM,
                source_adapter="hackernews",
                title="Teams cannot trace generated specs",
                content="Generated ideas often lose the source evidence.",
                url="https://example.com/signals/problem",
                tags=["lineage", "evidence"],
                credibility=0.8,
                metadata={"signal_role": "problem"},
            )
        )
        store.insert_signal(
            Signal(
                id="sig-lineage-market",
                source_type=SignalSourceType.ARTICLE,
                source_adapter="rss",
                title="Audit trails are now expected",
                content="Buyers ask for traceability in AI workflows.",
                url="https://example.com/signals/market",
                tags=["audit"],
                credibility=0.9,
                metadata={"signal_role": "market"},
            )
        )
        store.insert_signal(
            Signal(
                id="sig-lineage-direct",
                source_type=SignalSourceType.SURVEY,
                source_adapter="survey",
                title="Direct customer evidence",
                content="Customers want graph exports.",
                url="https://example.com/signals/direct",
                tags=["customer"],
                credibility=0.75,
            )
        )
        store.insert_insight(
            Insight(
                id="ins-lineage",
                category=InsightCategory.GAP,
                title="Evidence lineage gap",
                summary="Generated ideas need visible provenance.",
                evidence=["sig-lineage-problem", "sig-lineage-market"],
                confidence=0.86,
                domains=["devtools"],
            )
        )
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-lineage",
                title="Lineage Graph Export",
                one_liner="Graph provenance for generated ideas",
                category=BuildableCategory.APPLICATION,
                ideation_mode=IdeationMode.DIRECT,
                problem="Teams cannot inspect idea provenance.",
                solution="Expose a graph-shaped lineage endpoint.",
                value_proposition="Make generated ideas auditable.",
                inspiring_insights=["ins-lineage"],
                evidence_signals=["sig-lineage-direct"],
                domain="devtools",
                status="evaluated",
            )
        )
    finally:
        store.close()


def test_idea_lineage_graph_returns_nodes_edges_and_evidence_links(lineage_client) -> None:
    client, db_path = lineage_client
    _seed_lineage(db_path)

    response = client.get("/api/v1/ideas/bu-lineage/lineage")

    assert response.status_code == 200
    data = response.json()
    assert data["idea_id"] == "bu-lineage"

    nodes = {node["id"]: node for node in data["nodes"]}
    assert set(nodes) == {
        "idea:bu-lineage",
        "buildable_unit:bu-lineage",
        "insight:ins-lineage",
        "signal:sig-lineage-problem",
        "signal:sig-lineage-market",
        "signal:sig-lineage-direct",
    }
    assert nodes["idea:bu-lineage"]["entity_id"] == "bu-lineage"
    assert nodes["idea:bu-lineage"]["type"] == "idea"
    assert nodes["idea:bu-lineage"]["label"] == "Lineage Graph Export"
    assert nodes["buildable_unit:bu-lineage"]["type"] == "buildable_unit"
    assert nodes["buildable_unit:bu-lineage"]["label"] == "Graph provenance for generated ideas"
    assert nodes["insight:ins-lineage"]["type"] == "insight"
    assert nodes["insight:ins-lineage"]["label"] == "Evidence lineage gap"
    assert nodes["signal:sig-lineage-problem"]["type"] == "signal"
    assert nodes["signal:sig-lineage-problem"]["label"] == "Teams cannot trace generated specs"

    assert nodes["signal:sig-lineage-problem"]["evidence_links"] == [
        "https://example.com/signals/problem"
    ]
    assert set(nodes["insight:ins-lineage"]["evidence_links"]) == {
        "https://example.com/signals/problem",
        "https://example.com/signals/market",
    }
    assert set(nodes["buildable_unit:bu-lineage"]["evidence_links"]) == {
        "https://example.com/signals/problem",
        "https://example.com/signals/market",
        "https://example.com/signals/direct",
    }

    edges = {(edge["source"], edge["target"], edge["type"]) for edge in data["edges"]}
    assert edges == {
        ("idea:bu-lineage", "buildable_unit:bu-lineage", "materialized_as"),
        ("buildable_unit:bu-lineage", "insight:ins-lineage", "inspired_by"),
        ("insight:ins-lineage", "signal:sig-lineage-problem", "supported_by"),
        ("insight:ins-lineage", "signal:sig-lineage-market", "supported_by"),
        ("buildable_unit:bu-lineage", "signal:sig-lineage-direct", "direct_evidence"),
    }
    assert all(edge["id"] for edge in data["edges"])
    assert all(edge["label"] for edge in data["edges"])


def test_idea_lineage_graph_returns_404_for_unknown_idea(lineage_client) -> None:
    client, _ = lineage_client

    response = client.get("/api/v1/ideas/missing/lineage")

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"

