from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis import (
    build_design_brief_investor_update as exported_build_investor_update,
    render_design_brief_investor_update_csv as exported_render_investor_update_csv,
)
from max.analysis.design_brief_investor_update import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_investor_update,
    investor_update_filename,
    render_design_brief_investor_update,
    render_design_brief_investor_update_csv,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def test_build_design_brief_investor_update_is_deterministic_for_representative_input(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_investor_update(store, brief_id)
        repeated = build_design_brief_investor_update(store, brief_id)
        exported = exported_build_investor_update(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated == exported
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["buyer"] == "VP of Revenue Operations"
    assert report["design_brief"]["source_idea_ids"] == [
        "bu-investor-lead",
        "bu-investor-support",
    ]
    assert report["summary"]["confidence_level"] in {"medium", "high"}
    assert report["traction_signals"]
    assert any(signal["id"] == "evaluation" for signal in report["traction_signals"])
    assert any(
        "Customer interviews" in item["learning"]
        for item in report["learnings_since_last_review"]
    )
    assert report["top_risks"][0]["risk"] == "Revenue attribution needs validation"
    assert any("Fund or unblock validation" in item["ask"] for item in report["asks"])
    assert report["next_milestones"][0]["milestone"] == "Generate weekly investor update"
    assert json.loads(json.dumps(report))["kind"] == KIND


def test_sparse_design_brief_uses_stable_fallbacks(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_investor_update(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["confidence"]["level"] == "low"
    assert report["design_brief"]["buyer"] == "TBD buyer"
    assert report["traction_signals"][0]["id"] == "readiness"
    assert report["learnings_since_last_review"][0]["category"] == "fallback"
    assert report["top_risks"][0]["risk"] == (
        "Risk profile is under-specified for an investor or executive review"
    )
    assert any(
        "Attach at least three independent evidence" in item["ask"]
        for item in report["asks"]
    )
    assert [item["id"] for item in report["next_milestones"]] == ["M1", "M2", "M3"]


def test_render_design_brief_investor_update_markdown_json_and_filename(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_investor_update(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_investor_update(report, fmt="markdown")
    assert markdown.startswith("# Investor Update: Investor Update Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Summary" in markdown
    assert "## Traction Signals" in markdown
    assert "## Learnings Since Last Review" in markdown
    assert "## Top Risks" in markdown
    assert "## Asks" in markdown
    assert "## Next Milestones" in markdown
    assert "Revenue attribution needs validation" in markdown
    assert "{'" not in markdown
    assert "[{" not in markdown

    rendered_json = render_design_brief_investor_update(report, fmt="json")
    assert json.loads(rendered_json) == report

    with pytest.raises(ValueError, match="Unsupported investor update format: yaml"):
        render_design_brief_investor_update(report, fmt="yaml")

    assert (
        investor_update_filename(
            {"id": "dbf/investor 001", "title": "Investor Update: Alpha / Beta"}
        )
        == "dbf-investor-001-Investor-Update-Alpha-Beta-investor-update.md"
    )
    assert (
        investor_update_filename(
            {"id": "dbf/investor 001", "title": "Investor Update: Alpha / Beta"},
            fmt="json",
        )
        == "dbf-investor-001-Investor-Update-Alpha-Beta-investor-update.json"
    )
    assert (
        investor_update_filename(
            {"id": "dbf/investor 001", "title": "Investor Update: Alpha / Beta"},
            fmt="csv",
        )
        == "dbf-investor-001-Investor-Update-Alpha-Beta-investor-update.csv"
    )


def test_render_design_brief_investor_update_csv_full_output_is_stable(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_investor_update(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_text = render_design_brief_investor_update(report, fmt="csv")
    repeated = render_design_brief_investor_update_csv(report)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == repeated == exported_render_investor_update_csv(report)
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert csv.DictReader(StringIO(csv_text)).fieldnames == list(CSV_COLUMNS)
    assert [row["update_section"] for row in rows] == [
        "summary",
        "confidence",
        *["traction_signals"] * len(report["traction_signals"]),
        *["learnings_since_last_review"] * len(report["learnings_since_last_review"]),
        *["top_risks"] * len(report["top_risks"]),
        *["asks"] * len(report["asks"]),
        *["next_milestones"] * len(report["next_milestones"]),
        *["evidence_references"] * len(report["evidence_references"]),
    ]
    assert all(row["design_brief_id"] == brief_id for row in rows)
    assert all(row["design_brief_title"] == "Investor Update Brief" for row in rows)

    summary = rows[0]
    assert summary["update_section"] == "summary"
    assert summary["metric_name"] == "summary"
    assert summary["status_or_value"] == report["summary"]["confidence_level"]
    assert "Investor Update Brief is approved" in summary["narrative"]
    assert summary["risks_blockers"] == str(report["summary"]["risk_count"])
    assert summary["asks"] == str(report["summary"]["ask_count"])
    assert "sig-investor-review" in summary["evidence_source_references"]
    assert summary["source_idea_ids"] == "bu-investor-lead; bu-investor-support"

    traction = next(row for row in rows if row["metric_name"] == "evaluation")
    assert traction["update_section"] == "traction_signals"
    assert traction["status_or_value"] == "high"
    assert traction["evidence_source_references"] == "bu-investor-lead.evaluation"

    risk = next(row for row in rows if row["update_section"] == "top_risks")
    assert risk["status_or_value"] == "high"
    assert risk["risks_blockers"] == "Revenue attribution needs validation"
    assert "Pilot with three portfolio reviewers" in risk["narrative"]

    ask = next(row for row in rows if row["update_section"] == "asks" and row["metric_name"] == "A2")
    assert ask["status_or_value"] == "VP of Revenue Operations"
    assert ask["asks"].startswith("Fund or unblock validation")

    evidence = next(row for row in rows if row["update_section"] == "evidence_references")
    assert evidence["metric_name"].startswith("design_brief.")
    assert evidence["evidence_source_references"] == evidence["metric_name"]


def test_render_design_brief_investor_update_csv_handles_missing_optional_fields() -> None:
    report = {
        "design_brief": {
            "id": "dbf-partial",
            "title": 'Partial "Investor", Update',
        },
        "traction_signals": [
            {
                "id": "quoted",
                "signal": 'Pipeline signal includes "quotes", commas, and newline\ntext.',
            }
        ],
        "top_risks": [{"id": "R1", "risk": "Budget blocker"}],
        "asks": [{"id": "A1", "ask": "Approve next step"}],
    }

    csv_text = render_design_brief_investor_update_csv(report)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert '"Partial ""Investor"", Update"' in csv_text
    assert rows[0]["update_section"] == "traction_signals"
    assert rows[0]["status_or_value"] == ""
    assert rows[0]["narrative"] == 'Pipeline signal includes "quotes", commas, and newline\ntext.'
    assert rows[0]["evidence_source_references"] == ""
    assert rows[1]["update_section"] == "top_risks"
    assert rows[1]["risks_blockers"] == "Budget blocker"
    assert rows[1]["narrative"] == ""
    assert rows[2]["update_section"] == "asks"
    assert rows[2]["asks"] == "Approve next step"
    assert rows[2]["status_or_value"] == ""


def test_render_design_brief_investor_update_csv_empty_updates_header_only() -> None:
    report = {
        "design_brief": {
            "id": "dbf-empty",
            "title": "Empty Investor Update",
            "source_idea_ids": [],
        },
        "summary": {},
        "confidence": {},
        "traction_signals": [],
        "learnings_since_last_review": [],
        "top_risks": [],
        "asks": [],
        "next_milestones": [],
        "evidence_references": [],
    }

    header_only = render_design_brief_investor_update(report, fmt="csv")

    assert header_only == ",".join(CSV_COLUMNS) + "\n"
    assert csv.DictReader(StringIO(header_only)).fieldnames == list(CSV_COLUMNS)


def test_build_design_brief_investor_update_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_investor_update.db"), wal_mode=True)
    try:
        report = build_design_brief_investor_update(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_investor_update_{sparse}.db"),
        wal_mode=True,
    )
    if sparse:
        lead = BuildableUnit(
            id="bu-investor-sparse",
            title="Sparse Investor Update",
            one_liner="Create investor update defaults.",
            category="application",
            problem="Stakeholder updates need structure.",
            solution="Generate an update from sparse brief fields.",
            value_proposition="",
            specific_user="",
            buyer="",
            workflow_context="",
            current_workaround="",
            validation_plan="",
            first_10_customers="",
            domain_risks=[],
            evidence_rationale="",
            evidence_signals=[],
            inspiring_insights=[],
            tech_approach="",
            domain="operations",
            status="approved",
        )
        supporting: list[Candidate] = []
        readiness_score = 18.0
        validation_plan = ""
        risks: list[str] = []
        milestones: list[str] = []
        synthesis = ""
    else:
        lead = BuildableUnit(
            id="bu-investor-lead",
            title="Investor Update Lead",
            one_liner="Generate concise investor updates from design briefs.",
            category="application",
            problem="Portfolio reviewers cannot see traction, learnings, asks, and risks quickly.",
            solution="Create a deterministic investor update artifact.",
            value_proposition=(
                "Reduce portfolio review prep time and improve stakeholder alignment."
            ),
            specific_user="portfolio operations lead",
            buyer="VP of Revenue Operations",
            workflow_context="monthly portfolio review",
            current_workaround="manual slide updates compiled from scattered notes",
            why_now="Leadership is reviewing approved briefs for quarterly investment planning.",
            validation_plan="Pilot with three portfolio reviewers and measure review prep time.",
            first_10_customers="10 revenue operations teams",
            domain_risks=["Revenue attribution needs validation."],
            evidence_rationale=(
                "Customer interviews show executive review packets miss decision asks."
            ),
            evidence_signals=["sig-investor-review", "sig-investor-budget"],
            inspiring_insights=["ins-investor-ops"],
            tech_approach="Deterministic Python artifact over persisted brief fields.",
            domain="operations",
            status="approved",
        )
        support = BuildableUnit(
            id="bu-investor-support",
            title="Investor Update Support",
            one_liner="Trace update asks to validation and evidence.",
            category="automation",
            problem="Executives lack consistent follow-through on portfolio asks.",
            solution="Attach asks, milestones, and risks to update artifacts.",
            value_proposition="Make stakeholder asks auditable across review cycles.",
            specific_user="chief of staff",
            buyer="VP of Revenue Operations",
            workflow_context="investment committee handoff",
            current_workaround="spreadsheet tracker",
            validation_plan="Review update with budget owners before implementation.",
            first_10_customers="revenue leaders running monthly portfolio reviews",
            domain_risks=["Budget owner may reject unvalidated impact claims."],
            evidence_rationale="Budget owners asked for clearer milestone and risk status.",
            evidence_signals=["sig-investor-owner"],
            domain="operations",
            status="approved",
        )
        supporting = [Candidate(unit=support)]
        readiness_score = 84.0
        validation_plan = "Pilot with three portfolio reviewers and measure review prep time."
        risks = [
            "Revenue attribution needs validation.",
            "Budget owner may reject unvalidated impact claims.",
        ]
        milestones = [
            "Generate weekly investor update",
            "Review traction and asks with budget owner",
            "Publish next milestone decision",
        ]
        synthesis = (
            "Customer interviews and budget-owner evidence support a concise update format."
        )

    store.insert_buildable_unit(lead)
    store.insert_evaluation(_evaluation(lead.id, 82.0 if not sparse else 24.0))
    for candidate in supporting:
        store.insert_buildable_unit(candidate.unit)
        store.insert_evaluation(_evaluation(candidate.unit.id, 78.0))

    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Investor Update Brief",
            domain="operations",
            theme="portfolio-review",
            lead=Candidate(unit=lead),
            supporting=supporting,
            readiness_score=readiness_score,
            why_this_now=(
                "" if sparse else "Approved design briefs need concise stakeholder communication."
            ),
            merged_product_concept="A deterministic investor update for persisted design briefs.",
            synthesis_rationale=synthesis,
            mvp_scope=["Investor update JSON", "Investor update Markdown"],
            first_milestones=milestones,
            validation_plan=validation_plan,
            risks=risks,
            source_idea_ids=[lead.id, *[candidate.unit.id for candidate in supporting]],
            design_status="approved",
        )
    )
    return store, brief_id


def _evaluation(unit_id: str, overall_score: float) -> UtilityEvaluation:
    dim = DimensionScore(value=8.0, confidence=0.8, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=overall_score,
        recommendation="yes" if overall_score >= 70 else "hold",
    )
