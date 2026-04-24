"""API tests for MCP quality certification endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "api-mcp-quality.db")
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


def _seed_quality_data(db_path: str) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-api-quality-files",
                source_type=SignalSourceType.REGISTRY,
                source_adapter="mcp_registry",
                title="Filesystem MCP server",
                content="Read files and directories",
                url="https://example.com/sig-api-quality-files",
                tags=["mcp", "filesystem"],
                credibility=0.9,
            )
        )
        store.insert_signal(
            Signal(
                id="sig-api-quality-security",
                source_type=SignalSourceType.SECURITY,
                source_adapter="mcp_security_import",
                title="MCP sandbox bypass",
                content="Scanner found sandbox bypass in filesystem server",
                url="https://example.com/sig-api-quality-security",
                tags=["mcp", "security", "severity:high"],
                metadata={"severity": "high", "server_name": "filesystem-mcp"},
                credibility=0.85,
            )
        )
        unit = BuildableUnit(
            id="bu-api-mcp-quality",
            title="Filesystem MCP Server",
            one_liner="MCP server for governed filesystem access",
            category=BuildableCategory.MCP_SERVER,
            ideation_mode=IdeationMode.DIRECT,
            problem="Agents need reliable file access.",
            solution="Expose scoped filesystem MCP tools.",
            target_users="agents",
            value_proposition="Controlled local automation",
            evidence_signals=["sig-api-quality-files", "sig-api-quality-security"],
            quality_score=8.0,
            tech_approach="Python MCP server with allowlists",
            domain="devtools",
            status="evaluated",
        )
        store.insert_buildable_unit(unit)
        store.insert_evaluation(_evaluation("bu-api-mcp-quality", 84.0))
    finally:
        store.close()


def _evaluation(unit_id: str, score: float) -> UtilityEvaluation:
    def dimension(value: float) -> DimensionScore:
        return DimensionScore(value=value, confidence=0.8, reasoning="api seeded")

    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dimension(8.0),
        addressable_scale=dimension(7.0),
        build_effort=dimension(8.0),
        composability=dimension(9.0),
        competitive_density=dimension(7.0),
        timing_fit=dimension(8.0),
        compounding_value=dimension(8.0),
        overall_score=score,
        recommendation="yes",
    )


def test_global_mcp_quality_certification_endpoint_returns_schema(client, db_path) -> None:
    _seed_quality_data(db_path)

    resp = client.get("/api/v1/mcp/quality-certification")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "global"
    assert data["idea_id"] is None
    assert data["score"] > 0
    assert data["grade"] in {"A", "B", "C", "D", "F", "blocked"}
    assert isinstance(data["blockers"], list)
    assert "High severity MCP security finding lowers certification grade." in data["warnings"]
    assert {component["name"] for component in data["score_components"]} == {
        "capability",
        "reliability",
        "security",
        "idea_evaluation",
    }
    assert any(ref["id"] == "sig-api-quality-files" for ref in data["evidence_references"])
    assert any(ref["kind"] == "evaluation" for ref in data["evidence_references"])


def test_idea_mcp_quality_certification_endpoint_scopes_to_known_idea(client, db_path) -> None:
    _seed_quality_data(db_path)

    resp = client.get("/api/v1/ideas/bu-api-mcp-quality/mcp-quality-certification")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "idea"
    assert data["idea_id"] == "bu-api-mcp-quality"
    assert data["blocked"] is False
    assert {ref["id"] for ref in data["evidence_references"]} >= {
        "sig-api-quality-files",
        "sig-api-quality-security",
        "bu-api-mcp-quality",
    }
    assert all(ref["id"] != "bu-missing" for ref in data["evidence_references"])


def test_idea_mcp_quality_certification_endpoint_returns_404_for_unknown_idea(client) -> None:
    resp = client.get("/api/v1/ideas/bu-missing/mcp-quality-certification")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Idea not found: bu-missing"
