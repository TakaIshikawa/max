"""API tests for design brief support playbook exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_support_playbook import SCHEMA_VERSION
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
            id="bu-support-playbook-api",
            title="Support Playbook API Lead",
            one_liner="Expose support playbook handoffs over REST",
            category="application",
            problem="REST consumers cannot read support playbooks.",
            solution="Return structured support playbooks and Markdown exports from the API.",
            value_proposition="Make operational handoffs available to support automation.",
            specific_user="support engineer",
            buyer="support lead",
            workflow_context="pilot support intake",
            why_now="Support teams need deterministic handoff artifacts before rollout.",
            validation_plan="Review generated support playbooks with support owners.",
            domain_risks=["Security review can delay support access."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Support Playbook API Brief",
                domain="developer-tools",
                theme="support-playbook-rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=84.0,
                why_this_now="REST access lets support tooling consume playbooks.",
                merged_product_concept="A support playbook export for persisted design briefs.",
                synthesis_rationale="Covers operational handoff after product planning.",
                mvp_scope=["Support playbook JSON", "Support playbook Markdown"],
                first_milestones=["Return support playbook JSON"],
                validation_plan="Confirm support owners can resolve pilot tickets.",
                risks=["Security review can delay support access."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_support_playbook_returns_structured_playbook(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_support_playbook_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/support-playbook")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.support_playbook"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "Support Playbook API Brief"
    assert payload["design_brief"]["source_idea_ids"] == ["bu-support-playbook-api"]
    assert payload["summary"]["target_user"] == "support engineer"
    assert payload["onboarding_checks"]
    assert payload["support_scenarios"]
    assert payload["troubleshooting_flows"]
    assert payload["escalation_criteria"]
    assert payload["response_snippets"]
    assert payload["monitoring_signals"]


def test_get_design_brief_support_playbook_markdown_returns_downloadable_markdown(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_support_playbook_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/support-playbook.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-support-playbook.md"'
    )
    assert response.text.startswith("# Support Playbook: Support Playbook API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "Source ideas: bu-support-playbook-api" in response.text
    assert "## Support Context" in response.text
    assert "## Troubleshooting Flows" in response.text


def test_get_design_brief_support_playbook_missing_brief_returns_404_without_unrelated_builds(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = str(tmp_path / "design_brief_support_playbook_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    def fail_unrelated_build(*_args, **_kwargs):
        raise AssertionError("unrelated design brief analysis builder was called")

    monkeypatch.setattr(
        "max.server.api.build_design_brief_pricing_strategy",
        fail_unrelated_build,
    )
    monkeypatch.setattr(
        "max.server.api.build_design_brief_technical_feasibility",
        fail_unrelated_build,
    )
    monkeypatch.setattr(
        "max.server.api.build_design_brief_evidence_matrix",
        fail_unrelated_build,
    )

    json_response = client.get("/api/v1/design-briefs/dbf-missing/support-playbook")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/support-playbook.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
