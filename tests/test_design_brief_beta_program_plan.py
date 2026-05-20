from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_beta_program_plan import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_beta_program_plan,
    render_design_brief_beta_program_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_beta_program_plan_structured_output(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_beta_program_plan(store, brief_id)
        repeated = build_design_brief_beta_program_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["target_user"] == "platform lead"
    assert report["summary"]["buyer"] == "engineering director"
    assert report["summary"]["workflow_context"] == "internal developer platform adoption"
    assert report["summary"]["fallbacks_used"] == []
    assert report["summary"]["source_evidence_count"] == 2
    assert [cohort["id"] for cohort in report["beta_cohorts"]] == [
        "cohort-1",
        "cohort-2",
        "cohort-3",
    ]
    assert [item["id"] for item in report["eligibility_criteria"]] == [
        "EL1",
        "EL2",
        "EL3",
        "EL4",
    ]
    assert [item["id"] for item in report["feedback_cadence"]] == [
        "FC1",
        "FC2",
        "FC3",
        "FC4",
    ]
    assert [item["id"] for item in report["exit_criteria"]] == [
        "EX1",
        "EX2",
        "EX3",
        "EX4",
    ]
    assert [item["id"] for item in report["risk_mitigations"]] == ["RM1", "RM2"]
    assert "Privacy review" in report["risk_mitigations"][0]["risk"]
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_sparse_design_brief_beta_program_plan_uses_title_fallbacks(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_beta_program_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
    ]
    assert report["summary"]["target_user"] == "Sparse Beta Brief users"
    assert report["summary"]["buyer"] == "Sparse Beta Brief sponsor"
    assert report["summary"]["workflow_context"] == "Sparse Beta Brief validation workflow"
    assert report["beta_cohorts"][0]["participants"] == "Sparse Beta Brief users"
    assert report["eligibility_criteria"][1]["criterion"] == (
        "Beta use is limited to the smallest testable product behavior."
    )
    assert report["risk_mitigations"][0]["risk"] == (
        "Beta feedback is too thin to justify expansion."
    )


def test_build_design_brief_beta_program_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_beta_program.db"), wal_mode=True)
    try:
        report = build_design_brief_beta_program_plan(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def test_render_design_brief_beta_program_plan_json_markdown_csv_and_invalid(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_beta_program_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(render_design_brief_beta_program_plan(report, fmt="json")) == report

    markdown = render_design_brief_beta_program_plan(report, fmt="markdown")
    assert markdown.startswith("# Beta Program Plan: Beta Program Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Program Summary" in markdown
    assert "## Beta Cohorts" in markdown
    assert "### cohort-1: Design Partner Beta" in markdown
    assert "## Eligibility Criteria" in markdown
    assert "## Feedback Cadence" in markdown
    assert "## Exit Criteria" in markdown
    assert "## Risk Mitigations" in markdown
    assert "- Fallbacks used: none" in markdown

    csv_text = render_design_brief_beta_program_plan(report, fmt="csv")
    repeated = render_design_brief_beta_program_plan(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text == repeated
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(rows) == 3 + 4 + 4 + 4 + 2
    assert [row["section"] for row in rows[:3]] == ["beta_cohorts"] * 3
    assert rows[0]["design_brief_id"] == brief_id
    assert rows[0]["name"] == "Design Partner Beta"
    assert rows[3]["section"] == "eligibility_criteria"
    assert rows[7]["section"] == "feedback_cadence"
    assert rows[11]["section"] == "exit_criteria"
    assert rows[15]["section"] == "risk_mitigations"

    with pytest.raises(ValueError, match="Unsupported beta program plan format: yaml"):
        render_design_brief_beta_program_plan(report, fmt="yaml")


def test_render_design_brief_beta_program_plan_csv_escapes_values(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_beta_program_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report["beta_cohorts"][0]["name"] = 'Design, "Partner"\nBeta'

    csv_text = render_design_brief_beta_program_plan(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert '"Design, ""Partner""\nBeta"' in csv_text
    assert rows[0]["name"] == 'Design, "Partner"\nBeta'


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"beta_program_{sparse}.db"), wal_mode=True)
    if sparse:
        lead = BuildableUnit(
            id="bu-beta-sparse-lead",
            title="Sparse Beta Lead",
            one_liner="Generate sparse beta program plans.",
            category="application",
            problem="Beta planning needs explicit fallbacks.",
            solution="Build a beta program report with stable fallback values.",
            value_proposition="Make beta readiness visible.",
            specific_user="",
            buyer="",
            workflow_context="",
            validation_plan="",
            domain_risks=[],
            evidence_signals=[],
            inspiring_insights=[],
            domain="developer-tools",
            status="approved",
        )
        risks: list[str] = []
        mvp_scope: list[str] = []
    else:
        lead = BuildableUnit(
            id="bu-beta-lead",
            title="Beta Program Lead",
            one_liner="Plan controlled beta programs from persisted design briefs.",
            category="application",
            problem="Generated project specs do not describe early user validation.",
            solution="Export a deterministic beta program artifact.",
            value_proposition="Help product teams validate ideas before broad launch.",
            specific_user="platform lead",
            buyer="engineering director",
            workflow_context="internal developer platform adoption",
            current_workaround="manual beta docs",
            why_now="Design briefs already persist validation inputs.",
            validation_plan="Run a four-week beta with structured feedback.",
            first_10_customers="internal platform teams",
            domain_risks=["Privacy review is required before customer workflow data is used."],
            evidence_signals=["sig-beta"],
            inspiring_insights=["ins-beta"],
            tech_approach="FastAPI route using deterministic analysis code.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        risks = ["Privacy review is required before customer workflow data is used."]
        mvp_scope = ["Beta plan JSON", "Beta plan Markdown"]

    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Beta Brief" if sparse else "Beta Program Brief",
            domain="developer-tools",
            theme="beta-program",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=42.0 if sparse else 86.0,
            why_this_now="Generated project specs need beta planning.",
            merged_product_concept="A beta program export for persisted design briefs.",
            synthesis_rationale="Connects validation, cohorts, and release decisions.",
            mvp_scope=mvp_scope,
            first_milestones=["Return beta plan JSON", "Return beta plan Markdown"],
            validation_plan=""
            if sparse
            else "Confirm beta JSON and Markdown are actionable for product handoff.",
            risks=risks,
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
