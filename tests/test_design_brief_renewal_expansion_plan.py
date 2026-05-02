from __future__ import annotations

import json

import pytest

from max.analysis import (
    build_design_brief_renewal_expansion_plan as exported_build,
)
from max.analysis.design_brief_renewal_expansion_plan import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_renewal_expansion_plan,
    render_design_brief_renewal_expansion_plan,
    renewal_expansion_plan_filename,
    write_design_brief_renewal_expansion_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def test_renewal_expansion_plan_is_stable_and_traceable(tmp_path) -> None:
    store = Store(str(tmp_path / "renewal.db"))
    try:
        brief_id = _seed_renewal_brief(store)
        report = build_design_brief_renewal_expansion_plan(store, brief_id)
        repeated = build_design_brief_renewal_expansion_plan(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["buyer"] == "VP of Customer Operations"
    assert report["design_brief"]["specific_user"] == "customer success manager"
    assert report["design_brief"]["workflow_context"] == "weekly renewal health review"
    assert report["summary"]["renewal_health"] in {"healthy", "watch"}
    assert report["summary"]["missing_input_count"] == 0
    assert report["summary"]["evidence_signal_count"] == 2
    assert report["renewal_risks"][0]["id"] == "RR1"
    assert [item["id"] for item in report["expansion_triggers"]][:2] == ["ET1", "ET2"]
    assert [item["id"] for item in report["customer_success_motions"]] == [
        "CSM1",
        "CSM2",
        "CSM3",
    ]
    assert report["proof_points"][0]["strength"] == "strong"
    assert [item["id"] for item in report["next_actions"]] == ["NA1", "NA2", "NA3"]
    assert exported_build is build_design_brief_renewal_expansion_plan


def test_renewal_expansion_plan_sparse_brief_returns_missing_input_warnings(
    tmp_path,
) -> None:
    store = Store(str(tmp_path / "renewal_sparse.db"))
    try:
        brief_id = _seed_sparse_renewal_brief(store)
        report = build_design_brief_renewal_expansion_plan(store, brief_id)
        missing = build_design_brief_renewal_expansion_plan(store, "dbf-missing")
    finally:
        store.close()

    assert missing is None
    assert report is not None
    assert report["summary"]["renewal_health"] == "at_risk"
    assert report["summary"]["missing_input_count"] >= 7
    assert report["proof_points"][0]["id"] == "PP0"
    assert report["renewal_risks"][0]["id"] == "RR0"
    assert "Missing persisted fields" in report["renewal_risks"][0]["reason"]
    assert {item["field"] for item in report["missing_inputs"]} >= {
        "buyer",
        "specific_user",
        "workflow_context",
        "value_proposition",
        "validation_plan",
        "mvp_scope",
        "first_milestones",
    }


def test_render_renewal_expansion_plan_markdown_json_write_and_invalid_format(
    tmp_path,
) -> None:
    store = Store(str(tmp_path / "renewal_render.db"))
    try:
        brief_id = _seed_renewal_brief(store)
        report = build_design_brief_renewal_expansion_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_renewal_expansion_plan(report)
    assert markdown.startswith("# Renewal and Expansion Plan: Renewal Expansion Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Kind: `{KIND}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Renewal Risks" in markdown
    assert "## Expansion Opportunities" in markdown
    assert "## Customer Success Motions" in markdown
    assert "## Proof Points" in markdown
    assert "## Next Actions" in markdown
    assert "## Missing Inputs" in markdown

    assert json.loads(render_design_brief_renewal_expansion_plan(report, "json")) == report
    with pytest.raises(ValueError, match="Unsupported renewal expansion plan format: yaml"):
        render_design_brief_renewal_expansion_plan(report, "yaml")

    filename = renewal_expansion_plan_filename(
        {"id": "dbf-renewal-001", "title": "Renewal / Expansion Plan"},
        fmt="markdown",
    )
    assert filename == "dbf-renewal-001-Renewal-Expansion-Plan-renewal-expansion-plan.md"
    path = tmp_path / filename
    write_design_brief_renewal_expansion_plan(path, report)
    assert path.read_text(encoding="utf-8").startswith("# Renewal and Expansion Plan")
    assert renewal_expansion_plan_filename(
        {"id": "dbf-renewal-001", "title": "Renewal / Expansion Plan"},
        fmt="json",
    ).endswith(".json")


def _seed_renewal_brief(store: Store) -> str:
    store.insert_signal(
        Signal(
            id="sig-renewal-activation",
            source_type=SignalSourceType.SURVEY,
            source_adapter="test",
            title="Weekly activation evidence",
            content="Pilot teams use the workflow weekly and report renewal value.",
            url="https://example.com/activation",
            tags=["activation", "renewal"],
            credibility=0.92,
        )
    )
    store.insert_signal(
        Signal(
            id="sig-renewal-expansion",
            source_type=SignalSourceType.MARKET,
            source_adapter="test",
            title="Expansion interview",
            content="Buyer wants multi-team rollout after the first workflow proof.",
            url="https://example.com/expansion",
            tags=["expansion", "workflow"],
            credibility=0.86,
        )
    )
    lead = BuildableUnit(
        id="bu-renewal-lead",
        title="Renewal Lead",
        one_liner="Plan renewal and expansion from launch proof.",
        category="application",
        problem="Teams miss renewal signals after customer launch.",
        solution="Track activation, buyer proof, and expansion triggers.",
        value_proposition="Increase retention by making renewal value visible.",
        specific_user="customer success manager",
        buyer="VP of Customer Operations",
        workflow_context="weekly renewal health review",
        current_workaround="manual spreadsheets and account notes",
        why_now="Customer teams need recurring renewal evidence before expansion asks.",
        validation_plan="Run a 30-day pilot and measure activation, value proof, and renewal intent.",
        first_10_customers="B2B SaaS customer success teams",
        domain_risks=["Support handoff must not create unresolved ticket backlog."],
        evidence_signals=["sig-renewal-activation", "sig-renewal-expansion"],
        inspiring_insights=[],
        domain="customer-success",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Renewal Expansion Brief",
            domain="customer-success",
            theme="renewal-expansion",
            lead=Candidate(unit=lead),
            readiness_score=88.0,
            why_this_now="Renewal reviews need activation proof before account expansion.",
            merged_product_concept="A renewal planning artifact for customer success handoff.",
            synthesis_rationale="Connects launch proof, support risk, and expansion triggers.",
            mvp_scope=["Activation scorecard", "Renewal proof recap", "Expansion trigger log"],
            first_milestones=["Ship renewal recap", "Review first expansion trigger"],
            validation_plan="Measure weekly use, renewal intent, and buyer-visible value.",
            risks=["Support handoff must not create unresolved ticket backlog."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )


def _seed_sparse_renewal_brief(store: Store) -> str:
    lead = BuildableUnit(
        id="bu-renewal-sparse",
        title="Sparse Renewal Lead",
        one_liner="Sparse source for renewal planning fallbacks.",
        category="application",
        problem="",
        solution="",
        value_proposition="",
        specific_user="",
        buyer="",
        workflow_context="",
        current_workaround="",
        why_now="",
        validation_plan="",
        first_10_customers="",
        domain_risks=[],
        evidence_signals=[],
        inspiring_insights=[],
        domain="",
        status="draft",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Sparse Renewal Brief",
            domain="",
            theme="",
            lead=Candidate(unit=lead),
            readiness_score=20.0,
            why_this_now="",
            merged_product_concept="",
            synthesis_rationale="",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="draft",
        )
    )
