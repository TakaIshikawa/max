"""API tests for batch spec bundle export."""

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
def spec_bundle_batch_db(tmp_path) -> str:
    db_path = str(tmp_path / "spec_bundle_batch_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-batch001",
                source_type=SignalSourceType.FORUM,
                source_adapter="test",
                title="Batch bundle signal",
                content="Evidence that multiple approved ideas need one batch handoff.",
                url="https://example.com/spec-bundle-batch",
                credibility=0.81,
            )
        )
        store.insert_insight(
            Insight(
                id="ins-batch001",
                category=InsightCategory.GAP,
                title="Batch bundle insight",
                summary="Downstream automation avoids repeated calls when bundles are batched.",
                evidence=["sig-batch001"],
                confidence=0.83,
                domains=["testing"],
            )
        )
        store.insert_buildable_unit(_batch_unit("bu-batch001", "Batch Bundle One"))
        store.insert_evaluation(_batch_evaluation("bu-batch001"))
        store.insert_buildable_unit(_batch_unit("bu-batch002", "Batch Bundle Two"))
        store.insert_evaluation(_batch_evaluation("bu-batch002"))
        store.insert_buildable_unit(_batch_unit("bu-batch-noeval", "Batch Bundle No Eval"))
    finally:
        store.close()
    return db_path


@pytest.fixture
def spec_bundle_batch_client(spec_bundle_batch_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=spec_bundle_batch_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_post_spec_bundle_batch_returns_results_in_request_order(
    spec_bundle_batch_client: TestClient,
) -> None:
    response = spec_bundle_batch_client.post(
        "/api/v1/ideas/spec-bundle-batch",
        json={"idea_ids": ["bu-batch002", "bu-missing", "bu-batch001"], "format": "json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["idea_id"] for item in payload["results"]] == [
        "bu-batch002",
        "bu-missing",
        "bu-batch001",
    ]
    assert payload["results"][0]["status"] == "generated"
    assert payload["results"][0]["success"] is True
    assert payload["results"][0]["status_code"] == 200
    assert payload["results"][0]["bundle"]["idea_id"] == "bu-batch002"
    assert payload["results"][0]["markdown"] is None
    assert payload["results"][1] == {
        "idea_id": "bu-missing",
        "status": "not_found",
        "success": False,
        "status_code": 404,
        "bundle": None,
        "markdown": None,
        "error": "Idea not found: bu-missing",
    }
    assert payload["results"][2]["bundle"]["artifacts"]["spec_preview"]["project"]["title"] == (
        "Batch Bundle One"
    )


def test_post_spec_bundle_batch_markdown_returns_rendered_text_per_success(
    spec_bundle_batch_client: TestClient,
) -> None:
    response = spec_bundle_batch_client.post(
        "/api/v1/ideas/spec-bundle-batch",
        json={"idea_ids": ["bu-batch001", "bu-missing"], "format": "markdown"},
    )

    assert response.status_code == 200
    payload = response.json()
    first = payload["results"][0]
    assert first["status"] == "generated"
    assert first["bundle"] is None
    assert first["markdown"].startswith("# Batch Bundle One Implementation Packet")
    assert "## Spec Preview" in first["markdown"]
    assert "## Review Gate" in first["markdown"]
    assert payload["results"][1]["status"] == "not_found"
    assert payload["results"][1]["status_code"] == 404


def test_post_spec_bundle_batch_without_evaluation_returns_warning_item(
    spec_bundle_batch_client: TestClient,
) -> None:
    response = spec_bundle_batch_client.post(
        "/api/v1/ideas/spec-bundle-batch",
        json={"idea_ids": ["bu-batch-noeval"], "format": "json"},
    )

    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["status"] == "generated"
    assert item["success"] is True
    assert item["status_code"] == 200
    assert any("Utility evaluation is missing" in warning for warning in item["bundle"]["warnings"])
    assert item["bundle"]["artifacts"]["spec_preview"]["evaluation"] is None


def _batch_unit(unit_id: str, title: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner="Generate one batch implementation packet",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Automation issues many spec bundle requests before implementation starts.",
        solution="Expose a batch REST endpoint for implementation spec bundles.",
        target_users="agents",
        value_proposition="Faster autonomous implementation handoff.",
        specific_user="implementation agent operator",
        buyer="platform lead",
        workflow_context="pre-build handoff preparation",
        current_workaround="manual repeated endpoint calls",
        why_now="more approved ideas are handed to autonomous agents",
        validation_plan="call the batch endpoint and verify ordered results",
        first_10_customers="internal implementation agents",
        domain_risks=["large response bodies"],
        evidence_rationale="Evidence shows consumers need stable handoff artifacts.",
        inspiring_insights=["ins-batch001"],
        evidence_signals=["sig-batch001"],
        tech_approach="FastAPI endpoint that composes existing deterministic artifacts",
        suggested_stack={"language": "python", "framework": "fastapi"},
        composability_notes="No new persistence; bundles are generated on request.",
    )


def _batch_evaluation(unit_id: str) -> UtilityEvaluation:
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
