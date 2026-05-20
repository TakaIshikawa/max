from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_support_escalation_plan import build_design_brief_support_escalation_plan, render_design_brief_support_escalation_plan, support_escalation_plan_filename
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_support_escalation_plan_includes_required_sections_and_high_severity(tmp_path) -> None:
    store, brief_id = _store(tmp_path)
    try:
        report = build_design_brief_support_escalation_plan(store, brief_id)
        repeated = build_design_brief_support_escalation_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert report == repeated
    assert json.loads(json.dumps(report)) == report
    assert set(report) >= {"escalation_triggers", "severity_levels", "owner_handoffs", "runbook_requirements", "customer_messaging", "evidence_references", "evidence_gaps", "open_questions"}
    assert any(item["severity"] == "high" for item in report["escalation_triggers"])
    assert report["summary"]["high_severity_count"] >= 1


def test_support_escalation_plan_sparse_brief_reports_required_gaps(tmp_path) -> None:
    store, brief_id = _store(tmp_path, sparse=True)
    try:
        report = build_design_brief_support_escalation_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert [gap["id"] for gap in report["evidence_gaps"]] == ["missing_support_owner", "missing_failure_modes", "missing_customer_communication"]


def test_support_escalation_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_support_escalation_plan(store, "missing") is None
    finally:
        store.close()


def test_support_escalation_plan_renderers_and_filename(tmp_path) -> None:
    store, brief_id = _store(tmp_path)
    try:
        report = build_design_brief_support_escalation_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert json.loads(render_design_brief_support_escalation_plan(report, "json")) == report
    markdown = render_design_brief_support_escalation_plan(report)
    assert markdown.startswith("# Support Escalation Plan: Support Escalation Brief")
    assert "## Escalation Triggers" in markdown
    assert "## Customer Messaging" in markdown
    assert support_escalation_plan_filename(report["design_brief"]) == f"{brief_id}-Support-Escalation-Brief-support-escalation-plan.md"
    with pytest.raises(ValueError, match="Unsupported support escalation plan format"):
        render_design_brief_support_escalation_plan(report, "yaml")


def _store(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"support_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-support-lead",
        title="Support Lead",
        one_liner="Escalate high-risk support incidents.",
        category="application",
        problem="Support needs customer incident escalation for blocked workflows.",
        solution="Severity mapping, owner handoffs, runbooks, and customer messaging.",
        value_proposition="Reduce incident confusion.",
        specific_user="" if sparse else "support lead",
        buyer="" if sparse else "Head of Support",
        workflow_context="" if sparse else "customer incident support workflow",
        validation_plan="" if sparse else "Simulate a high risk customer incident and status update.",
        evidence_signals=[] if sparse else ["support incident review", "customer status template"],
        domain_risks=[] if sparse else ["High risk customer impact incident can block launch."],
        domain="support",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Escalation Brief" if sparse else "Support Escalation Brief",
            domain="support",
            theme="support-escalation",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=19.0 if sparse else 82.0,
            why_this_now="Customer incident handling needs clear support escalation.",
            merged_product_concept="Support escalation plan with runbooks and customer messaging.",
            synthesis_rationale="Connects support triggers to owner handoffs.",
            mvp_scope=[] if sparse else ["Define severity mapping", "Publish customer status template"],
            first_milestones=[] if sparse else ["Run incident tabletop", "Approve support runbook"],
            validation_plan="" if sparse else "Simulate a high risk customer incident and status update.",
            risks=[] if sparse else ["High risk customer impact incident can block launch."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
