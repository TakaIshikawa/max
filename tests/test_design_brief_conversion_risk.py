"""Tests for design brief pilot-to-paid conversion risk reports."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis import (
    build_design_brief_conversion_risk as exported_build_conversion_risk,
)
from max.analysis.design_brief_conversion_risk import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_conversion_risk,
    conversion_risk_filename,
    render_design_brief_conversion_risk,
    render_design_brief_conversion_risk_csv,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_conversion_risk_is_stable_and_traceable(tmp_path) -> None:
    store, brief_id = _store_with_conversion_brief(tmp_path)
    try:
        report = build_design_brief_conversion_risk(store, brief_id)
        repeated = build_design_brief_conversion_risk(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["target_buyer"] == "VP of Revenue Operations"
    assert report["summary"]["target_user"] == "sales operations manager"
    assert report["summary"]["workflow_context"] == "pilot handoff to paid rollout"
    assert report["summary"]["fallbacks_used"] == []
    assert report["summary"]["risk_band"] in {"low", "medium"}
    assert report["summary"]["conversion_gate"] in {
        "ready_for_paid_pilot",
        "run_targeted_validation_before_paid_ask",
        "resolve_blockers_before_conversion_ask",
    }
    assert report["conversion_blockers"]
    assert report["proof_gaps"][0]["id"] == "PG1"
    assert [item["id"] for item in report["buyer_objections"]] == ["BO1", "BO2", "BO3"]
    assert [item["id"] for item in report["mitigation_actions"]] == ["MA1", "MA2", "MA3"]
    assert all(item["validation_step"] for item in report["conversion_blockers"])
    assert json.loads(json.dumps(report))["kind"] == KIND
    assert exported_build_conversion_risk is build_design_brief_conversion_risk


def test_build_design_brief_conversion_risk_sparse_brief_has_actionable_fallbacks(
    tmp_path,
) -> None:
    store, brief_id = _store_with_conversion_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_conversion_risk(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["risk_band"] == "high"
    assert report["summary"]["conversion_gate"] == "resolve_blockers_before_conversion_ask"
    assert report["summary"]["fallbacks_used"] == [
        "buyer",
        "target_user",
        "workflow_context",
        "value_proposition",
        "current_workaround",
    ]
    assert report["proof_gaps"][0]["id"] == "PG0"
    assert "Missing persisted fields" in report["proof_gaps"][0]["gap"]
    assert report["validation_experiments"][0]["id"] == "EXP0"
    assert any(
        blocker["label"] == "Buyer Clarity" and blocker["validation_step"]
        for blocker in report["conversion_blockers"]
    )


def test_render_design_brief_conversion_risk_markdown_json_and_invalid_format(
    tmp_path,
) -> None:
    store, brief_id = _store_with_conversion_brief(tmp_path)
    try:
        report = build_design_brief_conversion_risk(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_conversion_risk(report)
    assert markdown.startswith("# Conversion Risk Report: Conversion Risk Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Kind: `{KIND}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "Risk band: `" in markdown
    assert "## Conversion Blockers" in markdown
    assert "## Proof Gaps" in markdown
    assert "## Buyer Objections" in markdown
    assert "## Mitigation Actions" in markdown
    assert "## Validation Experiments" in markdown

    parsed = json.loads(render_design_brief_conversion_risk(report, fmt="json"))
    assert parsed == report

    with pytest.raises(ValueError, match="Unsupported conversion risk format: yaml"):
        render_design_brief_conversion_risk(report, fmt="yaml")


def test_render_design_brief_conversion_risk_csv_rows_headers_and_order(tmp_path) -> None:
    store, brief_id = _store_with_conversion_brief(tmp_path)
    try:
        report = build_design_brief_conversion_risk(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_output = render_design_brief_conversion_risk(report, fmt="csv")
    repeated = render_design_brief_conversion_risk_csv(report)
    reader = csv.DictReader(io.StringIO(csv_output))
    rows = list(reader)

    assert csv_output == repeated
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert csv_output.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert [row["funnel_stage"] for row in rows] == [
        *(["conversion_gate"] * len(report["conversion_blockers"])),
        *(["proof_validation"] * len(report["proof_gaps"])),
        *(["buyer_objection"] * len(report["buyer_objections"])),
    ]
    assert rows[0]["risk"].startswith(f"{report['conversion_blockers'][0]['label']}: ")
    assert rows[0]["severity"] == report["conversion_blockers"][0]["severity"]
    assert rows[0]["likelihood"] == report["summary"]["risk_band"]
    assert rows[0]["affected_persona"] == "VP of Revenue Operations"
    assert rows[0]["mitigation"]
    assert rows[0]["leading_indicator"] == report["conversion_blockers"][0]["validation_step"]
    assert rows[0]["owner"]
    assert rows[0]["evidence"]


def test_render_design_brief_conversion_risk_csv_escapes_and_blanks_optional_fields() -> None:
    report = {
        "summary": {
            "risk_band": "high",
            "target_buyer": 'VP, "Growth"',
            "target_user": "sales\nops",
        },
        "conversion_context": {"buyer": 'VP, "Growth"'},
        "conversion_blockers": [
            {
                "id": "CB1",
                "label": "Budget, Timing",
                "severity": "high",
                "summary": 'Buyer said "not now"\nuntil proof exists.',
                "validation_step": "Confirm budget,\nand legal owner.",
                "source_reference_ids": ["idea,1", "sig\n2"],
            }
        ],
        "proof_gaps": [
            {
                "id": "PG1",
                "claim": "Paid conversion proof",
                "gap": "No owner named.",
                "needed_evidence": "Capture approver quote.",
                "source_reference_ids": [],
            }
        ],
        "buyer_objections": [
            {
                "id": "BO1",
                "objection": "Why pay now?",
                "likely_from": "",
                "response": "",
                "proof_needed": "Deadline evidence",
                "source_reference_ids": ["idea-1"],
            }
        ],
        "mitigation_actions": [],
    }

    csv_output = render_design_brief_conversion_risk_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_output)))

    assert rows[0]["risk"] == 'Budget, Timing: Buyer said "not now"\nuntil proof exists.'
    assert rows[0]["affected_persona"] == 'VP, "Growth"'
    assert rows[0]["mitigation"] == ""
    assert rows[0]["owner"] == ""
    assert rows[0]["leading_indicator"] == "Confirm budget,\nand legal owner."
    assert rows[0]["evidence"] == "idea,1; sig\n2"
    assert rows[1]["evidence"] == ""
    assert rows[2]["affected_persona"] == 'VP, "Growth"'
    assert '"Budget, Timing: Buyer said ""not now""' in csv_output
    assert '"Confirm budget,\nand legal owner."' in csv_output


def test_build_design_brief_conversion_risk_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_conversion_risk.db"), wal_mode=True)
    try:
        report = build_design_brief_conversion_risk(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def test_conversion_risk_filename_uses_brief_id_and_title() -> None:
    brief = {"id": "dbf-test001", "title": "Pilot Conversion API Brief"}
    assert (
        conversion_risk_filename(brief, fmt="markdown")
        == "dbf-test001-Pilot-Conversion-API-Brief-conversion-risk.md"
    )
    assert (
        conversion_risk_filename(brief, fmt="json")
        == "dbf-test001-Pilot-Conversion-API-Brief-conversion-risk.json"
    )
    assert (
        conversion_risk_filename(brief, fmt="csv")
        == "dbf-test001-Pilot-Conversion-API-Brief-conversion-risk.csv"
    )


def _store_with_conversion_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_conversion_risk_{sparse}.db"),
        wal_mode=True,
    )
    if sparse:
        lead = BuildableUnit(
            id="bu-conversion-sparse",
            title="Sparse Conversion Lead",
            one_liner="Sparse source for conversion fallback behavior.",
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
            tech_approach="",
            suggested_stack={},
            domain="",
            status="draft",
        )
        validation_plan = ""
        risks: list[str] = []
        mvp_scope: list[str] = []
        first_milestones: list[str] = []
        readiness_score = 25.0
        design_status = "draft"
    else:
        lead = BuildableUnit(
            id="bu-conversion-lead",
            title="Conversion Risk Lead",
            one_liner="Predict whether pilots convert to paid rollout.",
            category="application",
            problem="Revenue teams run pilots but miss the paid conversion ask.",
            solution="Score buyer, proof, urgency, and objections before pilot kickoff.",
            value_proposition="Increase paid pilot conversion with validated buyer proof.",
            specific_user="sales operations manager",
            buyer="VP of Revenue Operations",
            workflow_context="pilot handoff to paid rollout",
            current_workaround="manual spreadsheets and informal buyer recaps",
            why_now="A launch deadline creates pressure to convert qualified pilots now.",
            validation_plan="Run five paid-pilot interviews and measure buyer commitment.",
            first_10_customers="B2B SaaS revenue teams with active pilot motions",
            domain_risks=[
                "Procurement approval may delay conversion.",
                "Security review can block rollout timing.",
            ],
            evidence_rationale="Interview evidence shows budget owners want proof before paid rollout.",
            evidence_signals=["sig-conversion-budget", "sig-conversion-proof"],
            inspiring_insights=["ins-conversion-urgency"],
            tech_approach="Deterministic JSON and Markdown conversion risk export.",
            suggested_stack={"backend": "FastAPI", "storage": "SQLite"},
            domain="sales",
            status="approved",
        )
        validation_plan = "Run five paid-pilot interviews and measure buyer commitment."
        risks = ["Procurement approval may delay conversion."]
        mvp_scope = ["Buyer proof scorecard", "Paid conversion recap"]
        first_milestones = ["Export conversion risk JSON"]
        readiness_score = 86.0
        design_status = "approved"

    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Conversion Risk Brief",
            domain="sales",
            theme="pilot-conversion",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=readiness_score,
            why_this_now=(
                "Revenue teams need conversion proof before launch deadlines."
                if not sparse
                else ""
            ),
            merged_product_concept=(
                "A deterministic pilot-to-paid conversion risk artifact."
                if not sparse
                else ""
            ),
            synthesis_rationale=(
                "Connects buyer authority, proof gaps, objections, mitigation, and experiments."
                if not sparse
                else ""
            ),
            mvp_scope=mvp_scope,
            first_milestones=first_milestones,
            validation_plan=validation_plan,
            risks=risks,
            source_idea_ids=[lead.id],
            design_status=design_status,
        )
    )
    return store, brief_id
