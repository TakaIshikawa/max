"""API tests for design brief unit economics exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.analysis.design_brief_unit_economics import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.server.dependencies import get_store
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
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


def _evaluation(unit_id: str) -> UtilityEvaluation:
    dim = DimensionScore(value=8.0, confidence=0.8, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=82.0,
        strengths=["repeatable buyer workflow"],
        weaknesses=["payback needs validation"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        signal = Signal(
            id="sig-unit-econ-api",
            source_type=SignalSourceType.SURVEY,
            source_adapter="survey-fixture",
            title="Unit economics validation",
            content="Budget owners need payback and cost-to-serve assumptions.",
            url="https://example.com/unit-economics",
            tags=["pricing", "economics"],
            credibility=0.8,
            metadata={"signal_role": "market"},
        )
        store.insert_signal(signal)
        lead = BuildableUnit(
            id="bu-unit-econ-api",
            title="Unit Economics API Lead",
            one_liner="Expose design brief unit economics over REST.",
            category="application",
            problem="Dashboards cannot retrieve unit economics for approved design briefs.",
            solution="Return deterministic unit economics as JSON and Markdown.",
            value_proposition="Reduce approval friction with payback and cost-to-serve bands.",
            specific_user="portfolio operations lead",
            buyer="VP of Customer Operations",
            workflow_context="quarterly portfolio planning",
            current_workaround="manual spreadsheet unit economics modeling",
            why_now="Approved briefs need external automation for investment review.",
            validation_plan="Review willingness-to-pay and payback windows with budget owners.",
            first_10_customers="10 regulated customer operations teams",
            domain_risks=["Usage-sensitive model costs could compress margins."],
            evidence_rationale="Operations leaders requested payback ranges for approved briefs.",
            evidence_signals=[signal.id],
            tech_approach="FastAPI endpoint backed by deterministic artifact generation.",
            suggested_stack={"language": "python", "model": "llm"},
            domain="operations",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_evaluation(_evaluation(lead.id))
        return store.insert_design_brief(
            ProjectBrief(
                title="Unit Economics API Brief",
                domain="operations",
                theme="economics-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=86.0,
                why_this_now="REST access lets dashboards consume unit economics artifacts.",
                merged_product_concept=(
                    "Expose deterministic design brief unit economics over JSON and Markdown."
                ),
                synthesis_rationale="Unit economics creates a stable planning artifact.",
                mvp_scope=["JSON unit economics endpoint", "Markdown unit economics export"],
                first_milestones=["Return structured unit economics from FastAPI"],
                validation_plan="Confirm REST payload matches the economics renderer.",
                risks=["Payback assumptions need buyer validation."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_unit_economics_returns_json(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_unit_economics_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/unit-economics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.unit_economics"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "Unit Economics API Brief"
    assert payload["assumptions"]
    assert payload["cost_drivers"]
    assert payload["payback_bands"]["expected_months"] > 0
    assert payload["payback_bands"]["gross_margin_band"]
    assert payload["risks"]
    assert payload["validation_questions"]
    assert payload["summary"]["evidence_signal_count"] == 1


def test_get_design_brief_unit_economics_markdown_format_query(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_unit_economics_markdown_query_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/unit-economics?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Unit-Economics-API-Brief-unit-economics.md"'
    )
    assert response.text.startswith("# Unit Economics: Unit Economics API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Assumptions" in response.text
    assert "## Cost Drivers" in response.text
    assert "## Payback Bands" in response.text
    assert "## Risks" in response.text
    assert "## Validation Questions" in response.text


def test_get_design_brief_unit_economics_markdown_download(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_unit_economics_markdown_download_api.db")
    brief_id = _seed_design_brief(db_path)
    client = _client(db_path)

    query_response = client.get(
        f"/api/v1/design-briefs/{brief_id}/unit-economics?format=markdown"
    )
    markdown_response = client.get(f"/api/v1/design-briefs/{brief_id}/unit-economics.md")

    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert markdown_response.text == query_response.text


def test_get_design_brief_unit_economics_missing_brief_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_unit_economics_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    json_response = client.get("/api/v1/design-briefs/dbf-missing/unit-economics")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/unit-economics.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_unit_economics_unsupported_format_returns_validation_error(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_unit_economics_invalid_format_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/unit-economics?format=yaml"
    )

    assert response.status_code == 422
