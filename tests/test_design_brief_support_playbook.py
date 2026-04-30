"""Tests for design brief support playbook generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_support_playbook import (
    SCHEMA_VERSION,
    build_design_brief_support_playbook,
    render_design_brief_support_playbook,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_support_playbook_translates_persisted_brief(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        playbook = build_design_brief_support_playbook(store, brief_id)
    finally:
        store.close()

    assert playbook is not None
    assert playbook["schema_version"] == SCHEMA_VERSION
    assert playbook["kind"] == "max.design_brief.support_playbook"
    assert playbook["design_brief"]["id"] == brief_id
    assert playbook["summary"]["target_user"] == "support engineer"
    assert playbook["summary"]["buyer"] == "support lead"
    assert playbook["summary"]["workflow_context"] == "pilot support intake"
    assert playbook["summary"]["primary_scope"] == "Support playbook JSON"
    assert playbook["summary"]["fallbacks_used"] == []
    assert [check["id"] for check in playbook["onboarding_checks"]] == [
        "OC1",
        "OC2",
        "OC3",
        "OC4",
    ]
    assert [scenario["id"] for scenario in playbook["support_scenarios"]] == [
        "SS1",
        "SS2",
        "SS3",
        "SS4",
    ]
    assert all(flow["steps"] for flow in playbook["troubleshooting_flows"])
    assert any(
        item["severity"] == "elevated" and "Security review" in item["escalate_when"]
        for item in playbook["escalation_criteria"]
    )
    assert [snippet["id"] for snippet in playbook["response_snippets"]] == [
        "RS1",
        "RS2",
        "RS3",
    ]
    assert [signal["id"] for signal in playbook["monitoring_signals"]] == [
        "MS1",
        "MS2",
        "MS3",
        "MS4",
        "MS5",
    ]
    assert json.loads(json.dumps(playbook))["design_brief"]["id"] == brief_id


def test_sparse_design_brief_returns_title_and_workflow_fallback_scenarios(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        playbook = build_design_brief_support_playbook(store, brief_id)
    finally:
        store.close()

    assert playbook is not None
    assert playbook["summary"]["target_user"] == "Sparse Support Brief user"
    assert playbook["summary"]["workflow_context"] == "Sparse Support Brief support workflow"
    assert playbook["summary"]["primary_scope"] == "first usable Sparse Support Brief workflow"
    assert playbook["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
    ]
    scenario_text = " ".join(
        f"{scenario['name']} {scenario['trigger']}"
        for scenario in playbook["support_scenarios"]
    )
    assert "Sparse Support Brief" in scenario_text
    assert "Sparse Support Brief support workflow" in scenario_text
    assert playbook["support_scenarios"][0]["trigger"].startswith(
        "Sparse Support Brief user cannot complete"
    )


def test_render_design_brief_support_playbook_markdown_and_json(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        playbook = build_design_brief_support_playbook(store, brief_id)
    finally:
        store.close()

    assert playbook is not None
    markdown = render_design_brief_support_playbook(playbook)

    assert markdown.startswith("# Support Playbook: Support Playbook Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Onboarding Checks" in markdown
    assert "## Support Scenarios" in markdown
    assert "## Troubleshooting Flows" in markdown
    assert "## Escalation Criteria" in markdown
    assert "## Response Snippets" in markdown
    assert "## Monitoring Signals" in markdown
    assert "### Elevated: Elevated risk path" in markdown

    rendered_json = render_design_brief_support_playbook(playbook, fmt="json")
    assert json.loads(rendered_json) == playbook
    with pytest.raises(ValueError):
        render_design_brief_support_playbook(playbook, fmt="yaml")


def test_build_design_brief_support_playbook_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_support_playbook.db"), wal_mode=True)
    try:
        playbook = build_design_brief_support_playbook(store, "dbf-missing")
    finally:
        store.close()

    assert playbook is None


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_support_playbook.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-support-playbook-lead",
        title="Support Playbook Lead",
        one_liner="Prepare customer support handoffs from design briefs.",
        category="application",
        problem="Generated specs do not include support readiness.",
        solution="Export deterministic support playbooks.",
        value_proposition="Make pilot support operational before customer exposure.",
        specific_user="support engineer",
        buyer="support lead",
        workflow_context="pilot support intake",
        current_workaround="manual support notes",
        why_now="Pilot handoff artifacts need operational coverage.",
        validation_plan="Run two supported pilots and review ticket evidence.",
        first_10_customers="developer platform support teams",
        domain_risks=["Security review can delay support access."],
        evidence_signals=["ticket-volume"],
        inspiring_insights=["support teams need scripted responses"],
        tech_approach="Python export module.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Support Playbook Brief",
            domain="developer-tools",
            theme="support-readiness",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=86.0,
            why_this_now="Generated project specs need support handoff artifacts.",
            merged_product_concept="A support playbook export for persisted design briefs.",
            synthesis_rationale="Covers operational handoff after PRD and roadmap.",
            mvp_scope=["Support playbook JSON", "Support playbook Markdown"],
            first_milestones=["Return support playbook JSON"],
            validation_plan="Confirm support owners can resolve pilot tickets.",
            risks=["Security review can delay support access."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_sparse_support_playbook.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-support-playbook-sparse",
        title="Sparse Support Lead",
        one_liner="Prepare support handoffs when brief fields are incomplete.",
        category="application",
        problem="Support readiness can be sparse.",
        solution="Use deterministic support fallbacks.",
        value_proposition="Keep support playbooks actionable with missing fields.",
        specific_user="",
        buyer="",
        workflow_context="",
        validation_plan="",
        domain_risks=[],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Support Brief",
            domain="developer-tools",
            theme="support-readiness",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=55.0,
            why_this_now="The team needs support fallback coverage.",
            merged_product_concept="A sparse support playbook.",
            synthesis_rationale="Tests explicit support fallbacks.",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="candidate",
        )
    )
    return store, brief_id
