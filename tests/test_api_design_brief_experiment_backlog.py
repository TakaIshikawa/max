"""API tests for design brief experiment backlog exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.analysis.design_brief_experiment_backlog import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.server.dependencies import get_store
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


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


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-experiment-backlog-api",
            title="Experiment Backlog API Lead",
            one_liner="Expose design brief experiment backlogs over REST",
            category="application",
            problem="Planning tools cannot consume generated experiment backlogs.",
            solution="Return structured experiment backlog artifacts and Markdown exports.",
            value_proposition="Make validation planning available to automation.",
            specific_user="product operations lead",
            buyer="product director",
            workflow_context="design brief validation planning",
            why_now="Design brief artifacts are already persisted and deterministic.",
            validation_plan="Review generated backlog items with product and research leads.",
            domain_risks=["Customer interviews may not reach budget owners."],
            domain="product-ops",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Experiment Backlog API Brief",
                domain="product-ops",
                theme="rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=86.0,
                why_this_now="Downstream planning tools need API access to validation experiments.",
                merged_product_concept=(
                    "Expose deterministic design brief experiment backlogs over JSON and Markdown."
                ),
                synthesis_rationale="The backlog module creates a stable planning artifact.",
                mvp_scope=["JSON experiment backlog endpoint", "Markdown experiment backlog export"],
                first_milestones=["Return structured backlog items from FastAPI"],
                validation_plan="Confirm the REST payload matches the backlog renderer.",
                risks=["Buyer urgency needs validation."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_experiment_backlog_returns_structured_report(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_experiment_backlog_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/experiment-backlog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.experiment_backlog"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["summary"]["backlog_item_count"] == len(payload["backlog_items"])
    assert payload["backlog_items"]
    assert payload["recommended_next_actions"]


def test_get_design_brief_experiment_backlog_markdown_format_query(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_experiment_backlog_markdown_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/experiment-backlog?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Experiment-Backlog-API-Brief-experiment-backlog.md"'
    )
    assert response.text.startswith("# Experiment Backlog: Experiment Backlog API Brief")
    assert "## Prioritized Experiments" in response.text
    assert "## Recommended Next Actions" in response.text


def test_get_design_brief_experiment_backlog_markdown_download(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_experiment_backlog_download_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/experiment-backlog.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# Experiment Backlog: Experiment Backlog API Brief")


def test_get_design_brief_experiment_backlog_missing_brief_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_experiment_backlog_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    json_response = client.get("/api/v1/design-briefs/dbf-missing/experiment-backlog")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/experiment-backlog.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_experiment_backlog_unsupported_format_returns_validation_error(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_experiment_backlog_invalid_format_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/experiment-backlog?format=yaml"
    )

    assert response.status_code == 422
