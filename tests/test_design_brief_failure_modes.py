"""Tests for design brief failure mode analysis generation."""

from __future__ import annotations

import json
import re

import pytest

from max.analysis.design_brief_failure_modes import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_failure_modes,
    failure_modes_filename,
    render_design_brief_failure_modes,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_failure_modes_structured_output(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_failure_modes(store, brief_id)
        repeated = build_design_brief_failure_modes(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["title"] == "Failure Modes Brief"
    assert report["design_brief"]["source_idea_ids"] == [
        "bu-failure-lead",
        "bu-failure-support",
    ]
    assert report["summary"]["failure_mode_count"] == len(report["failure_modes"])
    assert report["summary"]["top_risk_priority_number"] == report["failure_modes"][0][
        "risk_priority_number"
    ]
    assert report["summary"]["evidence_reference_count"] >= 1
    assert json.loads(json.dumps(report))["schema_version"] == SCHEMA_VERSION


def test_failure_modes_have_fmea_scores_and_are_ranked_by_rpn(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_failure_modes(store, brief_id)
    finally:
        store.close()

    assert report is not None
    modes = report["failure_modes"]
    rpns = [mode["risk_priority_number"] for mode in modes]
    assert rpns == sorted(rpns, reverse=True)
    assert [mode["rank"] for mode in modes] == list(range(1, len(modes) + 1))
    assert all(
        {
            "failure_mode",
            "cause",
            "effect",
            "detection_method",
            "mitigation",
            "severity",
            "likelihood",
            "detectability",
            "risk_priority_number",
            "owner_role",
            "source_references",
        }
        <= set(mode)
        for mode in modes
    )
    assert all(
        mode["risk_priority_number"]
        == mode["severity"] * mode["likelihood"] * mode["detectability"]
        for mode in modes
    )
    assert all(1 <= mode["severity"] <= 10 for mode in modes)
    assert all(1 <= mode["likelihood"] <= 10 for mode in modes)
    assert all(1 <= mode["detectability"] <= 10 for mode in modes)


def test_known_risks_assumptions_and_sources_are_reflected(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_failure_modes(store, brief_id)
    finally:
        store.close()

    assert report is not None
    modes = report["failure_modes"]
    assert any("Security review may block pilot launch" in mode["failure_mode"] for mode in modes)
    assert any("Legacy API sync can drop review state" in mode["failure_mode"] for mode in modes)
    assert any("target workflow, buyer path" in mode["cause"] for mode in modes)
    assert any("expert review" in mode["detection_method"].lower() for mode in modes)
    assert any("technical spike" in mode["detection_method"].lower() for mode in modes)
    assert any("launch gate" in mode["mitigation"].lower() for mode in modes)
    assert any(ref["source_idea_ids"] for mode in modes for ref in mode["source_references"])
    assert any(item["id"] == "sig-failure-1" for item in report["evidence_references"])


def test_markdown_renderer_sorts_highest_risk_modes_first(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_failure_modes(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_failure_modes(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_failure_modes(report, fmt="markdown")
    assert markdown.startswith("# Failure Modes: Failure Modes Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Prioritized Failure Modes" in markdown
    assert "Detection method:" in markdown
    assert "Mitigation:" in markdown
    assert "Source references:" in markdown
    assert "{'" not in markdown
    assert "[{" not in markdown

    rendered_rpns = [int(value) for value in re.findall(r"^### \d+\. .*\(RPN (\d+)\)$", markdown, re.M)]
    assert rendered_rpns == sorted(rendered_rpns, reverse=True)
    assert rendered_rpns[0] == report["failure_modes"][0]["risk_priority_number"]


def test_sparse_design_brief_returns_assumption_failure_modes(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_failure_modes(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert len(report["failure_modes"]) >= 4
    assert report["summary"]["fallbacks_used"] == ["specific_user", "buyer", "workflow_context"]
    assert {item["field"] for item in report["known_assumptions"]} >= {
        "specific_user",
        "buyer",
        "workflow_context",
        "validation_plan",
        "mvp_scope",
    }
    assert any(
        "evidence audit" in mode["detection_method"].lower()
        or "pass/fail validation rubric" in mode["detection_method"].lower()
        for mode in report["failure_modes"]
    )
    assert all(mode["mitigation"] for mode in report["failure_modes"])


def test_failure_modes_missing_brief_invalid_format_and_filename(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_failure_modes.db"), wal_mode=True)
    try:
        assert build_design_brief_failure_modes(store, "dbf-missing") is None
    finally:
        store.close()

    with pytest.raises(ValueError, match="Unsupported failure modes format: yaml"):
        render_design_brief_failure_modes({"design_brief": {}}, fmt="yaml")

    design_brief = {"id": "dbf-123", "title": "Failure Modes: Alpha / Beta"}
    assert (
        failure_modes_filename(design_brief)
        == "dbf-123-Failure-Modes-Alpha-Beta-failure-modes.md"
    )
    assert (
        failure_modes_filename(design_brief, fmt="json")
        == "dbf-123-Failure-Modes-Alpha-Beta-failure-modes.json"
    )


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_failure_modes.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-failure-lead",
        title="Failure Lead",
        one_liner="Identify failure modes before implementation tasks are generated.",
        category="application",
        problem="Agents need risk-ranked failure analysis before launch planning.",
        solution="Generate FMEA-style failure modes from persisted design briefs.",
        value_proposition="Reduce preventable launch and validation misses.",
        specific_user="implementation agent",
        buyer="VP of Product",
        workflow_context="pre-build launch review",
        current_workaround="manual risk review checklist",
        why_now="Design briefs already capture risks, validation plans, and scope.",
        validation_plan="Run a launch review with risk owners and require pass/fail decisions.",
        first_10_customers="product teams turning design briefs into implementation tasks",
        domain_risks=["Security review may block pilot launch."],
        evidence_signals=["sig-failure-1"],
        inspiring_insights=["ins-failure-1"],
        tech_approach="Deterministic Python scoring over design brief risk fields.",
        domain="developer-tools",
        status="approved",
    )
    supporting = BuildableUnit(
        id="bu-failure-support",
        title="Failure Support",
        one_liner="Tie failure detection to validation and launch actions.",
        category="application",
        problem="Risk notes often lack owners, detection methods, and mitigations.",
        solution="Attach owners, detection methods, and launch gates to each failure mode.",
        value_proposition="Make failure analysis actionable for implementation planning.",
        specific_user="product engineer",
        buyer="engineering director",
        workflow_context="implementation readiness review",
        current_workaround="spreadsheet risk register",
        domain_risks=["Legacy API sync can drop review state."],
        evidence_signals=["sig-failure-2"],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Failure Modes Brief",
            domain="developer-tools",
            theme="failure-modes",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=76.0,
            why_this_now="Agents need failure analysis before implementation handoff.",
            merged_product_concept="A failure modes artifact for persisted design briefs.",
            synthesis_rationale="Extends design briefs with risk priority and mitigation detail.",
            mvp_scope=["Failure modes JSON artifact", "Markdown failure modes export"],
            first_milestones=["Generate sorted FMEA report"],
            validation_plan="Run a launch review with risk owners and require pass/fail decisions.",
            risks=[
                "Security review may block pilot launch.",
                "Legacy API sync can drop review state.",
                "Buyer adoption may stall after initial validation.",
            ],
            source_idea_ids=[lead.id, supporting.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / "design_brief_sparse_failure_modes.db"), wal_mode=True
    )
    lead = BuildableUnit(
        id="bu-failure-sparse",
        title="Sparse Failure Lead",
        one_liner="Create failure modes with weak inputs.",
        category="application",
        problem="Failure analysis inputs are incomplete.",
        solution="Use conservative assumption failure modes.",
        value_proposition="Keep risks visible without pretending context is complete.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Failure Brief",
            domain="developer-tools",
            theme="failure-modes",
            lead=Candidate(unit=lead),
            readiness_score=32.0,
            why_this_now="",
            merged_product_concept="",
            synthesis_rationale="",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="candidate",
        )
    )
    return store, brief_id
