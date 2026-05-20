from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_partner_rollout_plan import build_design_brief_partner_rollout_plan, partner_rollout_plan_filename, render_design_brief_partner_rollout_plan
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_partner_rollout_plan_derives_segments_and_dependencies(tmp_path) -> None:
    store, brief_id = _store(tmp_path)
    try:
        report = build_design_brief_partner_rollout_plan(store, brief_id)
        repeated = build_design_brief_partner_rollout_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert report == repeated
    assert json.loads(json.dumps(report)) == report
    assert set(report) >= {"partner_segments", "enablement_assets", "integration_dependencies", "launch_gates", "support_handoffs", "evidence_references", "evidence_gaps", "source_ideas"}
    assert {segment["name"] for segment in report["partner_segments"]} >= {"Agency partners", "Channel partners", "Integration partners"}
    assert any(dep["id"] == "D2" for dep in report["integration_dependencies"])


def test_partner_rollout_plan_sparse_brief_reports_gaps(tmp_path) -> None:
    store, brief_id = _store(tmp_path, sparse=True)
    try:
        report = build_design_brief_partner_rollout_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert [gap["id"] for gap in report["evidence_gaps"]] == ["missing_partner_owner", "missing_partner_workflow", "missing_partner_validation"]


def test_partner_rollout_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_partner_rollout_plan(store, "missing") is None
    finally:
        store.close()


def test_partner_rollout_plan_markdown_sections_and_filename(tmp_path) -> None:
    store, brief_id = _store(tmp_path)
    try:
        report = build_design_brief_partner_rollout_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert json.loads(render_design_brief_partner_rollout_plan(report, "json")) == report
    markdown = render_design_brief_partner_rollout_plan(report)
    for heading in ("## Partner Scope", "## Rollout Gates", "## Dependencies", "## Support Handoffs", "## Evidence Gaps", "## Open Questions"):
        assert heading in markdown
    assert partner_rollout_plan_filename(report["design_brief"]) == f"{brief_id}-Partner-Rollout-Brief-partner-rollout-plan.md"
    with pytest.raises(ValueError, match="Unsupported partner rollout plan format"):
        render_design_brief_partner_rollout_plan(report, "yaml")


def _store(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"partner_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-partner-lead",
        title="Partner Lead",
        one_liner="Roll out agency channel integration.",
        category="application",
        problem="Agency and reseller channel partners need API integration rollout support.",
        solution="Partner enablement for channel API integration.",
        value_proposition="Launch partners faster.",
        specific_user="" if sparse else "partner solutions lead",
        buyer="" if sparse else "VP Partnerships",
        workflow_context="" if sparse else "agency reseller API rollout workflow",
        validation_plan="" if sparse else "Pilot with two agency partners and one channel reseller.",
        evidence_signals=[] if sparse else ["agency waitlist", "reseller integration request"],
        domain_risks=[] if sparse else ["Support handoff could miss partner integration failures."],
        domain="partnerships",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Partner Brief" if sparse else "Partner Rollout Brief",
            domain="partnerships",
            theme="partner-rollout",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=18.0 if sparse else 80.0,
            why_this_now="Channel and agency partners are waiting for integration access.",
            merged_product_concept="Partner rollout for API integration workflow.",
            synthesis_rationale="Combines agency enablement with reseller channel launch gates.",
            mvp_scope=[] if sparse else ["Create partner sandbox", "Publish integration guide"],
            first_milestones=[] if sparse else ["Select pilot partners", "Complete sandbox setup"],
            validation_plan="" if sparse else "Pilot with two agency partners and one channel reseller.",
            risks=[] if sparse else ["Support handoff could miss partner integration failures."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
