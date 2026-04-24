"""API tests for spec bundle Markdown export."""

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
def spec_bundle_markdown_db(tmp_path) -> str:
    db_path = str(tmp_path / "spec_bundle_markdown_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-md001",
                source_type=SignalSourceType.FORUM,
                source_adapter="test",
                title="Markdown signal",
                content="Evidence that agents need one Markdown handoff document.",
                url="https://example.com/spec-bundle-md",
                credibility=0.82,
            )
        )
        store.insert_insight(
            Insight(
                id="ins-md001",
                category=InsightCategory.GAP,
                title="Markdown insight",
                summary="Implementation agents need deterministic bundle sections.",
                evidence=["sig-md001"],
                confidence=0.84,
                domains=["testing"],
            )
        )
        store.insert_buildable_unit(_markdown_unit())
        store.insert_evaluation(_markdown_evaluation())
    finally:
        store.close()
    return db_path


@pytest.fixture
def spec_bundle_markdown_client(spec_bundle_markdown_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=spec_bundle_markdown_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_spec_bundle_markdown_export_success(
    spec_bundle_markdown_client: TestClient,
) -> None:
    response = spec_bundle_markdown_client.get("/api/v1/ideas/bu-md001/spec-bundle.md")

    assert response.status_code == 200
    assert response.text.startswith("# Markdown Bundle Implementation Packet")
    assert "## Spec Preview" in response.text
    assert "## Evidence Links" in response.text
    assert "- bu-md001 -> ins-md001 (inspired_by; inspires)" in response.text
    assert "- ins-md001 -> sig-md001 (supported_by; evidenced_by)" in response.text


def test_get_spec_bundle_markdown_export_headers(
    spec_bundle_markdown_client: TestClient,
) -> None:
    response = spec_bundle_markdown_client.get("/api/v1/ideas/bu-md001/spec-bundle.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        'attachment; filename="bu-md001-spec-bundle.md"'
    )


def test_get_spec_bundle_markdown_missing_idea(
    spec_bundle_markdown_client: TestClient,
) -> None:
    response = spec_bundle_markdown_client.get("/api/v1/ideas/bu-missing/spec-bundle.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: bu-missing"


def test_get_spec_bundle_markdown_section_order_is_stable(
    spec_bundle_markdown_client: TestClient,
) -> None:
    response = spec_bundle_markdown_client.get("/api/v1/ideas/bu-md001/spec-bundle.md")

    assert response.status_code == 200
    headings = [
        "## Warnings",
        "## Spec Preview",
        "## Readiness",
        "## Implementation Plan",
        "## Launch Checklist",
        "## Acceptance Criteria",
        "## Experiment Card",
        "## Risk Register",
        "## Review Gate",
        "## Evidence Density",
        "## Evidence Links",
        "## Evidence Chain Summary",
    ]
    positions = [response.text.index(heading) for heading in headings]
    assert positions == sorted(positions)


def _markdown_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-md001",
        title="Markdown Bundle",
        one_liner="Export one Markdown implementation packet",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Implementation agents need deterministic handoff packets.",
        solution="Expose a Markdown spec bundle endpoint generated from the existing bundle.",
        target_users="implementation agents",
        value_proposition="Faster external handoff with one stable document.",
        specific_user="implementation agent operator",
        buyer="platform lead",
        workflow_context="pre-build handoff",
        current_workaround="manual endpoint stitching",
        why_now="more implementation work is delegated to external systems",
        validation_plan="fetch the Markdown endpoint and verify section order",
        first_10_customers="internal implementation agents",
        domain_risks=["Markdown can drift from JSON bundle"],
        evidence_rationale="Evidence links show why the idea should be built.",
        inspiring_insights=["ins-md001"],
        evidence_signals=["sig-md001"],
        tech_approach="FastAPI endpoint that renders the existing spec bundle",
        suggested_stack={"language": "python", "framework": "fastapi"},
        composability_notes="No additional persistence is required.",
    )


def _markdown_evaluation() -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.78, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id="bu-md001",
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=83.0,
        strengths=["Stable Markdown handoff"],
        weaknesses=["Renderer needs ordering tests"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
