"""API tests for idea spec bundle export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def spec_bundle_db(tmp_path) -> str:
    db_path = str(tmp_path / "spec_bundle_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-bundle001",
                source_type=SignalSourceType.FORUM,
                source_adapter="test",
                title="Bundle signal",
                content="Evidence that users need one execution packet.",
                url="https://example.com/bundle",
                credibility=0.8,
            )
        )
        store.insert_insight(
            Insight(
                id="ins-bundle001",
                category=InsightCategory.GAP,
                title="Bundle insight",
                summary="Consumers fetch too many endpoints for handoff.",
                evidence=["sig-bundle001"],
                confidence=0.8,
                domains=["testing"],
            )
        )
        store.insert_buildable_unit(_bundle_unit("bu-bundle001"))
        store.insert_evaluation(_bundle_evaluation("bu-bundle001"))
        store.insert_buildable_unit(_bundle_unit("bu-noeval001"))
    finally:
        store.close()
    return db_path


@pytest.fixture
def spec_bundle_client(spec_bundle_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=spec_bundle_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_spec_bundle_json(spec_bundle_client: TestClient) -> None:
    response = spec_bundle_client.get("/api/v1/ideas/bu-bundle001/spec-bundle")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "max-spec-bundle/v1"
    assert payload["idea_id"] == "bu-bundle001"
    assert payload["generated_at"]
    assert payload["artifacts"]["spec_preview"]["project"]["title"] == "Bundle Idea"
    assert payload["artifacts"]["implementation_plan"]["schema_version"] == "max-implementation-plan/v1"
    assert payload["artifacts"]["review_gate"]["schema_version"] == "max-review-gate/v1"
    assert payload["artifacts"]["evidence_density"]["signal_count"] == 1
    assert payload["artifacts"]["evidence_chain_summary"]["insight_ids"] == ["ins-bundle001"]


def test_get_spec_bundle_without_evaluation_returns_warnings(spec_bundle_client: TestClient) -> None:
    response = spec_bundle_client.get("/api/v1/ideas/bu-noeval001/spec-bundle")

    assert response.status_code == 200
    payload = response.json()
    assert any("Utility evaluation is missing" in warning for warning in payload["warnings"])
    assert payload["artifacts"]["spec_preview"]["evaluation"] is None
    assert payload["artifacts"]["experiment_card"]["source"]["evaluation_available"] is False
    assert "utility evaluation is missing" in payload["artifacts"]["review_gate"]["blocking_reasons"]


def test_get_spec_bundle_markdown(spec_bundle_client: TestClient) -> None:
    response = spec_bundle_client.get("/api/v1/ideas/bu-bundle001/spec-bundle?format=markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# Bundle Idea Implementation Packet")
    assert "## Spec Preview" in response.text
    assert "## Review Gate" in response.text
    assert "## Evidence Chain Summary" in response.text


def test_get_spec_bundle_missing_idea(spec_bundle_client: TestClient) -> None:
    response = spec_bundle_client.get("/api/v1/ideas/bu-missing/spec-bundle")

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: bu-missing"


def _bundle_unit(unit_id: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Bundle Idea",
        one_liner="One packet for implementation handoff",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Execution consumers fetch many separate idea endpoints before implementation starts.",
        solution="Expose one bundle endpoint with every implementation artifact.",
        target_users="agents",
        value_proposition="Faster and more stable implementation handoff.",
        specific_user="implementation agent operator",
        buyer="platform lead",
        workflow_context="pre-build handoff preparation",
        current_workaround="manual endpoint stitching",
        why_now="more ideas are handed to autonomous agents",
        validation_plan="call the endpoint and verify downstream packet consumption",
        first_10_customers="internal implementation agents",
        domain_risks=["packet can become too large"],
        evidence_rationale="Evidence shows consumers need a stable handoff artifact.",
        inspiring_insights=["ins-bundle001"],
        evidence_signals=["sig-bundle001"],
        tech_approach="FastAPI endpoint that composes existing deterministic artifacts",
        suggested_stack={"language": "python", "framework": "fastapi"},
        composability_notes="No new persistence; bundle is generated on request.",
    )


def _bundle_evaluation(unit_id: str) -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.75, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=82.0,
        strengths=["Stable handoff"],
        weaknesses=["Bundle size needs monitoring"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
