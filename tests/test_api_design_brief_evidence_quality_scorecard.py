"""API tests for design brief evidence quality scorecard exports."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from max.analysis.design_brief_evidence_quality_scorecard import KIND, SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.server.dependencies import get_store
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _client(db_path: str) -> TestClient:
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_design_brief_evidence_quality_scorecard_returns_json(tmp_path) -> None:
    db_path = str(tmp_path / "evidence_quality_scorecard_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/evidence-quality-scorecard"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == KIND
    assert data["source"]["entity_type"] == "design_brief"
    assert data["source"]["id"] == brief_id
    assert data["design_brief"]["id"] == brief_id
    assert data["design_brief"]["title"] == "Evidence Quality API Brief"
    assert data["summary"]["overall_score"] > 0
    assert data["summary"]["band"] in {"ready", "monitor", "needs_evidence", "blocked"}
    assert {dimension["id"] for dimension in data["dimension_scores"]} == {
        "evidence_volume",
        "source_diversity",
        "recency",
        "role_balance",
        "contradiction_risk",
        "traceability",
    }
    assert data["evidence_refs"]["source_idea_ids"] == ["bu-evidence-api"]
    assert data["evidence_refs"]["signal_ids"] == [
        "sig-api-market",
        "sig-api-problem",
        "sig-api-risk",
        "sig-api-validation",
        "sig-api-workflow",
    ]


def test_get_design_brief_evidence_quality_scorecard_returns_markdown(tmp_path) -> None:
    db_path = str(tmp_path / "evidence_quality_scorecard_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    client = _client(db_path)

    response = client.get(
        f"/api/v1/design-briefs/{brief_id}/evidence-quality-scorecard?fmt=markdown"
    )
    markdown_response = client.get(
        f"/api/v1/design-briefs/{brief_id}/evidence-quality-scorecard.md"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text == markdown_response.text
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-evidence-quality-scorecard.md"'
    )
    assert response.text.startswith("# Evidence Quality Scorecard: Evidence Quality API Brief")
    assert "## Dimension Scores" in response.text
    assert "### Evidence Volume" in response.text
    assert "## Recommended Next Evidence Actions" in response.text
    assert "sig-api-problem" in response.text


def test_get_design_brief_evidence_quality_scorecard_missing_brief_returns_404(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = str(tmp_path / "evidence_quality_scorecard_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()

    def fail_build(*args, **kwargs):
        raise AssertionError("scorecard builder should not run for missing design briefs")

    monkeypatch.setattr(
        "max.server.api.build_design_brief_evidence_quality_scorecard",
        fail_build,
    )
    client = _client(db_path)

    response = client.get("/api/v1/design-briefs/dbf-missing/evidence-quality-scorecard")
    markdown_response = client.get(
        "/api/v1/design-briefs/dbf-missing/evidence-quality-scorecard.md"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_evidence_quality_scorecard_rejects_unsupported_format(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "evidence_quality_scorecard_format_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/evidence-quality-scorecard?fmt=html"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Unsupported evidence quality scorecard format: html. "
        "Supported formats: json, markdown"
    )


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        published_at = datetime(2026, 4, 20, tzinfo=timezone.utc)
        for signal in [
            _signal("sig-api-problem", "hackernews", "problem", published_at),
            _signal("sig-api-market", "stackoverflow_survey", "market", published_at),
            _signal("sig-api-workflow", "github_issues", "workflow", published_at),
            _signal("sig-api-risk", "nvd_cve", "risk", published_at),
            _signal("sig-api-validation", "product_hunt", "validation", published_at),
        ]:
            store.insert_signal(signal)

        store.insert_insight(
            Insight(
                id="ins-api-evidence",
                category=InsightCategory.GAP,
                title="Evidence traceability gap",
                summary="REST consumers need design brief evidence quality before build handoff.",
                evidence=["sig-api-problem", "sig-api-market", "sig-api-workflow"],
                confidence=0.88,
                domains=["developer-tools"],
            )
        )

        unit = BuildableUnit(
            id="bu-evidence-api",
            title="Evidence Quality API",
            one_liner="Expose evidence quality scorecards over REST.",
            category="application",
            problem="Agents cannot inspect design brief evidence quality without Python access.",
            solution="Serve deterministic evidence quality scorecards from the API.",
            value_proposition="Make evidence readiness visible before implementation starts.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="build assignment review for autonomous agents",
            why_now="Evidence traceability is central to design brief handoff.",
            validation_plan="Compare API output against the scorecard renderer.",
            evidence_signals=[
                "sig-api-problem",
                "sig-api-market",
                "sig-api-workflow",
                "sig-api-risk",
                "sig-api-validation",
            ],
            inspiring_insights=["ins-api-evidence"],
            domain_risks=["Traceability gaps may hide weak implementation evidence."],
            evidence_rationale="Recent signals cover problem, market, workflow, risk, and validation.",
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(unit)

        return store.insert_design_brief(
            ProjectBrief(
                title="Evidence Quality API Brief",
                domain="developer-tools",
                theme="evidence-quality-rest",
                lead=Candidate(unit=unit),
                readiness_score=88.0,
                why_this_now="REST consumers need scorecards before build execution.",
                merged_product_concept="A REST endpoint for persisted design brief evidence quality.",
                synthesis_rationale="The existing scorecard artifact should be available to API clients.",
                mvp_scope=["JSON scorecard endpoint", "Markdown scorecard export"],
                first_milestones=["Expose scorecard route", "Validate markdown rendering"],
                validation_plan="Run focused API tests against a persisted design brief.",
                risks=["Unsupported formats should fail clearly."],
                source_idea_ids=[unit.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def _signal(
    signal_id: str,
    adapter: str,
    role: str,
    published_at: datetime,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"{role.title()} evidence",
        content=f"Recent credible {role} evidence for REST scorecard handoff.",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.85,
        published_at=published_at,
        fetched_at=published_at,
        metadata={"signal_role": role},
    )
