from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_field_feedback_loop import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_field_feedback_loop,
    render_design_brief_field_feedback_loop,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_field_feedback_loop_structured_output(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_field_feedback_loop(store, brief_id)
        repeated = build_design_brief_field_feedback_loop(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["target_user"] == "support lead"
    assert report["summary"]["buyer"] == "customer success director"
    assert report["summary"]["workflow_context"] == "enterprise support escalation"
    assert report["summary"]["fallbacks_used"] == []
    assert report["summary"]["evidence_reference_count"] == 2
    assert [item["id"] for item in report["feedback_sources"]] == [
        "FS1",
        "FS2",
        "FS3",
        "FS4",
    ]
    assert [item["id"] for item in report["collection_prompts"]] == [
        "CP1",
        "CP2",
        "CP3",
        "CP4",
    ]
    assert [item["id"] for item in report["triage_rules"]] == [
        "TR1",
        "TR2",
        "TR3",
        "TR4",
    ]
    assert [item["id"] for item in report["routing_owners"]] == [
        "RO1",
        "RO2",
        "RO3",
        "RO4",
    ]
    assert [item["id"] for item in report["synthesis_cadence"]] == [
        "SC1",
        "SC2",
        "SC3",
    ]
    assert [item["id"] for item in report["decision_thresholds"]] == [
        "DT1",
        "DT2",
        "DT3",
        "DT4",
    ]
    assert report["evidence_references"][0]["text"] == "support escalations repeat weekly"
    assert json.loads(json.dumps(report))["design_brief"]["id"] == brief_id


def test_sparse_design_brief_field_feedback_loop_uses_stable_fallbacks(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_field_feedback_loop(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
    ]
    assert report["summary"]["target_user"] == "Sparse Field Feedback Brief users"
    assert report["summary"]["buyer"] == "Sparse Field Feedback Brief sponsor"
    assert report["summary"]["workflow_context"] == (
        "Sparse Field Feedback Brief field workflow"
    )
    assert report["evidence_references"] == [
        {
            "id": "ER1",
            "source_idea_id": "bu-field-sparse-lead",
            "source_title": "Sparse Field Feedback Brief",
            "kind": "fallback",
            "text": (
                "No persisted source evidence was available; collect first field evidence "
                "before changing launch scope."
            ),
        }
    ]
    assert "Sparse Field Feedback Brief users" in report["triage_rules"][0]["rule"]


def test_build_design_brief_field_feedback_loop_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_field_feedback.db"), wal_mode=True)
    try:
        report = build_design_brief_field_feedback_loop(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def test_render_design_brief_field_feedback_loop_json_markdown_csv_and_invalid(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_field_feedback_loop(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(render_design_brief_field_feedback_loop(report, fmt="json")) == report

    markdown = render_design_brief_field_feedback_loop(report, fmt="markdown")
    assert markdown.startswith("# Field Feedback Loop: Field Feedback Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Loop Summary" in markdown
    assert "## Feedback Sources" in markdown
    assert "## Collection Prompts" in markdown
    assert "## Triage Rules" in markdown
    assert "## Routing Owners" in markdown
    assert "## Synthesis Cadence" in markdown
    assert "## Decision Thresholds" in markdown
    assert "## Evidence References" in markdown
    assert "support escalations repeat weekly" in markdown

    csv_text = render_design_brief_field_feedback_loop(report, fmt="csv")
    repeated = render_design_brief_field_feedback_loop(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text == repeated
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(rows) == 4 + 4 + 4 + 4 + 3 + 4 + 2
    assert [row["section"] for row in rows[:4]] == ["feedback_sources"] * 4
    assert rows[0]["design_brief_id"] == brief_id
    assert rows[4]["section"] == "collection_prompts"
    assert rows[8]["section"] == "triage_rules"
    assert rows[12]["section"] == "routing_owners"
    assert rows[16]["section"] == "synthesis_cadence"
    assert rows[19]["section"] == "decision_thresholds"
    assert rows[23]["section"] == "evidence_references"

    with pytest.raises(ValueError, match="Unsupported field feedback loop format: yaml"):
        render_design_brief_field_feedback_loop(report, fmt="yaml")


def test_render_design_brief_field_feedback_loop_csv_escapes_values(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_field_feedback_loop(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report["feedback_sources"][0]["capture_method"] = 'Ask "why", then\nclassify.'

    csv_text = render_design_brief_field_feedback_loop(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert '"Ask ""why"", then\nclassify."' in csv_text
    assert rows[0]["rule_or_prompt"] == 'Ask "why", then\nclassify.'


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"field_feedback_{sparse}.db"), wal_mode=True)
    if sparse:
        lead = BuildableUnit(
            id="bu-field-sparse-lead",
            title="Sparse Field Lead",
            one_liner="Generate sparse field feedback loop plans.",
            category="application",
            problem="Field feedback needs explicit fallback handling.",
            solution="Build a feedback loop report with stable fallbacks.",
            value_proposition="Make field learning actionable.",
            specific_user="",
            buyer="",
            workflow_context="",
            validation_plan="",
            domain_risks=[],
            evidence_signals=[],
            inspiring_insights=[],
            domain="customer-success",
            status="approved",
        )
        risks: list[str] = []
        mvp_scope: list[str] = []
    else:
        lead = BuildableUnit(
            id="bu-field-lead",
            title="Field Feedback Lead",
            one_liner="Plan field feedback loops from persisted design briefs.",
            category="application",
            problem="Generated project specs lose customer-facing feedback.",
            solution="Export a deterministic field feedback loop artifact.",
            value_proposition="Help teams route field learning into specs.",
            specific_user="support lead",
            buyer="customer success director",
            workflow_context="enterprise support escalation",
            current_workaround="manual field notes",
            why_now="Design briefs already persist validation inputs.",
            validation_plan="Run field review with support, sales, and product.",
            first_10_customers="enterprise support teams",
            domain_risks=["Support notes can overrepresent one noisy account."],
            evidence_signals=["support escalations repeat weekly"],
            inspiring_insights=["buyers want escalation visibility before renewal"],
            tech_approach="FastAPI route using deterministic analysis code.",
            suggested_stack={"language": "python"},
            domain="customer-success",
            status="approved",
        )
        risks = ["Support notes can overrepresent one noisy account."]
        mvp_scope = ["Field feedback JSON", "Field feedback Markdown"]

    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Field Feedback Brief" if sparse else "Field Feedback Brief",
            domain="customer-success",
            theme="field-feedback",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=39.0 if sparse else 82.0,
            why_this_now="Generated project specs need field feedback planning.",
            merged_product_concept="A field feedback loop export for persisted design briefs.",
            synthesis_rationale="Connects customer signals, routing, and spec decisions.",
            mvp_scope=mvp_scope,
            first_milestones=["Return feedback loop JSON", "Return feedback loop Markdown"],
            validation_plan=""
            if sparse
            else "Confirm field feedback JSON and Markdown are actionable.",
            risks=risks,
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
