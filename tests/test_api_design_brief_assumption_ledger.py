"""API tests for design brief assumption ledger exports."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from max.analysis.design_brief_assumption_ledger import SCHEMA_VERSION
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
            id="bu-assumption-ledger-api",
            title="Assumption Ledger API Lead",
            one_liner="Expose design brief assumption ledgers over REST",
            category="application",
            problem="Dashboards cannot inspect design brief assumptions.",
            solution="Return structured assumption ledgers and Markdown exports from the API.",
            value_proposition="Make assumption risk visible to automation.",
            specific_user="platform engineer",
            buyer="VP of Engineering",
            workflow_context="agent release governance review",
            why_now="Agent releases are moving from experiments into production.",
            validation_plan="Interview platform engineers and engineering buyers before implementation.",
            domain_risks=[],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Assumption Ledger API Brief",
                domain="developer-tools",
                theme="assumption-ledger-rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=86.0,
                why_this_now="REST access lets dashboards consume the assumption ledger.",
                merged_product_concept=(
                    "A release governance brief that names assumptions before build."
                ),
                synthesis_rationale="The ledger module already creates a stable artifact.",
                mvp_scope=["JSON assumption ledger", "Markdown assumption ledger"],
                first_milestones=["Return structured assumption ledgers from FastAPI"],
                validation_plan="Confirm the REST payload matches the ledger renderer.",
                risks=["Security approval may block rollout."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_assumption_ledger_returns_structured_ledger(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_assumption_ledger_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/assumption-ledger")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.assumption_ledger"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "Assumption Ledger API Brief"
    assert payload["summary"]["assumption_count"] >= 8
    assert [group["id"] for group in payload["assumption_groups"]] == [
        "desirability",
        "feasibility",
        "viability",
        "go_to_market",
    ]
    first_assumption = payload["assumption_groups"][0]["assumptions"][0]
    assert first_assumption["id"] == "dba-desirability-01"
    assert first_assumption["confidence_level"] in {"medium", "high"}
    assert any(link["kind"] == "source_idea" for link in first_assumption["evidence_links"])
    assert payload["next_validation_actions"][0]["assumption_id"]


def test_get_design_brief_assumption_ledger_markdown_returns_downloadable_markdown(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_assumption_ledger_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/assumption-ledger.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-assumption-ledger.md"'
    )
    assert response.text.startswith("# Assumption Ledger: Assumption Ledger API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "### Desirability" in response.text
    assert "## Next Validation Actions" in response.text


def test_get_design_brief_assumption_ledger_markdown_format_query(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_assumption_ledger_format_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/assumption-ledger?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# Assumption Ledger: Assumption Ledger API Brief")


def test_get_design_brief_assumption_ledger_unsupported_format_uses_renderer_validation(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_assumption_ledger_invalid_format_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/assumption-ledger?format=yaml"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported assumption ledger format: yaml"


def test_get_design_brief_assumption_ledger_missing_brief_returns_404_without_rendering(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_assumption_ledger_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    with patch(
        "max.server.api.render_design_brief_assumption_ledger"
    ) as render, patch("max.server.api.build_design_brief_assumption_ledger") as build:
        json_response = client.get("/api/v1/design-briefs/dbf-missing/assumption-ledger")
        markdown_response = client.get("/api/v1/design-briefs/dbf-missing/assumption-ledger.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
    build.assert_not_called()
    render.assert_not_called()
