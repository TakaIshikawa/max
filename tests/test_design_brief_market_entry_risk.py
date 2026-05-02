from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis import (
    build_design_brief_market_entry_risk_report as exported_build_market_entry_risk_report,
)
from max.analysis.design_brief_market_entry_risk import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_market_entry_risk_report,
    market_entry_risk_report_filename,
    render_market_entry_risk_csv,
    render_design_brief_market_entry_risk_report,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_market_entry_risk_report_high_risk_with_structured_entries(tmp_path) -> None:
    store, brief_id = _store_with_market_entry_brief(tmp_path, "high")
    try:
        report = build_design_brief_market_entry_risk_report(store, brief_id)
        repeated = build_design_brief_market_entry_risk_report(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["summary"]["risk_band"] == "high"
    assert report["summary"]["high_risk_count"] >= 3
    assert [risk["category"] for risk in report["risks"]] == [
        "adoption_friction",
        "incumbent_competition",
        "channel_access",
        "switching_costs",
        "compliance_constraints",
        "timing_sensitivity",
    ]
    assert all(
        {"category", "severity", "evidence", "mitigation", "open_question"} <= set(risk)
        for risk in report["risks"]
    )
    assert report["signals"]["prior_art"][0]["title"] == "Enterprise Workflow Suite"
    assert exported_build_market_entry_risk_report is build_design_brief_market_entry_risk_report


def test_market_entry_risk_report_low_risk_with_clear_entry_path(tmp_path) -> None:
    store, brief_id = _store_with_market_entry_brief(tmp_path, "low")
    try:
        report = build_design_brief_market_entry_risk_report(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["risk_band"] == "low"
    assert report["summary"]["high_risk_count"] == 0
    assert report["summary"]["fallbacks_used"] == []
    assert {risk["severity"] for risk in report["risks"]} <= {"low", "medium"}
    assert report["open_questions"] == []


def test_market_entry_risk_report_sparse_input_uses_assumptions_and_questions(
    tmp_path,
) -> None:
    store, brief_id = _store_with_market_entry_brief(tmp_path, "sparse")
    try:
        report = build_design_brief_market_entry_risk_report(store, brief_id)
        missing = build_design_brief_market_entry_risk_report(store, "dbf-missing")
    finally:
        store.close()

    assert missing is None
    assert report is not None
    assert report["summary"]["risk_band"] in {"medium", "high"}
    assert report["summary"]["fallbacks_used"] == [
        "buyer",
        "target_user",
        "workflow_context",
        "value_proposition",
        "current_workaround",
    ]
    assert report["market_context"]["buyer"] == "economic buyer"
    assert report["summary"]["open_question_count"] >= 3
    assert any(risk["open_question"] for risk in report["risks"])


def test_render_market_entry_risk_report_markdown_json_and_invalid_format(tmp_path) -> None:
    store, brief_id = _store_with_market_entry_brief(tmp_path, "high")
    try:
        report = build_design_brief_market_entry_risk_report(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_market_entry_risk_report(report)
    assert markdown.startswith("# Market Entry Risk Report: High Market Entry Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Kind: `{KIND}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Market Context" in markdown
    assert "## Risk Entries" in markdown
    assert "### Adoption Friction" in markdown
    assert "## Mitigation Plan" in markdown
    assert "## Open Questions" in markdown

    assert json.loads(render_design_brief_market_entry_risk_report(report, "json")) == report
    assert render_design_brief_market_entry_risk_report(report, "csv") == render_market_entry_risk_csv(report)
    with pytest.raises(ValueError, match="Unsupported market entry risk report format: yaml"):
        render_design_brief_market_entry_risk_report(report, "yaml")


def test_render_market_entry_risk_report_csv_structured_rows_and_order(tmp_path) -> None:
    store, brief_id = _store_with_market_entry_brief(tmp_path, "high")
    try:
        report = build_design_brief_market_entry_risk_report(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_output = render_market_entry_risk_csv(report)
    repeated = render_design_brief_market_entry_risk_report(report, "csv")
    reader = csv.DictReader(io.StringIO(csv_output))
    rows = list(reader)

    assert csv_output == repeated
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert csv_output.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert [(row["section"], row["item_id"]) for row in rows[:6]] == [
        ("risk", "adoption_friction"),
        ("risk", "incumbent_competition"),
        ("risk", "channel_access"),
        ("risk", "switching_costs"),
        ("risk", "compliance_constraints"),
        ("risk", "timing_sensitivity"),
    ]

    risk_rows = {row["item_id"]: row for row in rows if row["section"] == "risk"}
    assert risk_rows["channel_access"]["design_brief_id"] == brief_id
    assert risk_rows["channel_access"]["risk_type"] == "channel_access"
    assert risk_rows["channel_access"]["severity"] == "high"
    assert risk_rows["channel_access"]["likelihood"] == "high"
    assert risk_rows["channel_access"]["impact"] == "55"
    assert risk_rows["channel_access"]["source_idea_ids"] == "bu-market-entry-high"
    assert "enterprise approval or procurement access constraints" in risk_rows["channel_access"]["details"]
    assert "Define the first reachable segment" in risk_rows["channel_access"]["mitigation"]

    mitigation_rows = [row for row in rows if row["section"] == "mitigation"]
    assert [(row["item_id"], row["risk_type"], row["owner"]) for row in mitigation_rows] == [
        ("MR1", "incumbent_competition", "Product Marketing"),
        ("MR2", "channel_access", "Go-to-Market"),
        ("MR3", "switching_costs", "Solutions"),
        ("MR4", "compliance_constraints", "Legal/Security"),
    ]

    assert any(
        row["section"] == "entry_assumption"
        and row["risk_type"] == "buyer"
        and row["details"] == "buyer: enterprise IT director"
        for row in rows
    )
    assert any(
        row["section"] == "evidence_reference"
        and row["risk_type"] == "prior_art"
        and row["source_idea_ids"] == "bu-market-entry-high"
        and "Enterprise Workflow Suite" in row["details"]
        for row in rows
    )
    assert any(
        row["section"] == "readiness_warning"
        and row["risk_type"] == "readiness_score"
        and row["severity"] == "medium"
        for row in rows
    )
    assert [row["item_id"] for row in rows if row["section"] == "next_action"] == [
        "NA1",
        "NA2",
        "NA3",
        "NA4",
    ]


def test_render_market_entry_risk_report_csv_escapes_special_values(tmp_path) -> None:
    store, brief_id = _store_with_market_entry_brief(tmp_path, "low")
    try:
        report = build_design_brief_market_entry_risk_report(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report["risks"][0]["evidence"] = ['Buyer said "yes",\nthen requested legal review.']
    report["risks"][0]["mitigation"] = 'Run a "fast follow", then document tradeoffs.'

    csv_output = render_market_entry_risk_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_output)))

    assert '"Adoption Friction; Buyer said ""yes"",\nthen requested legal review."' in csv_output
    assert '"Run a ""fast follow"", then document tradeoffs."' in csv_output
    assert rows[0]["details"] == 'Adoption Friction; Buyer said "yes",\nthen requested legal review.'
    assert rows[0]["mitigation"] == 'Run a "fast follow", then document tradeoffs.'


def test_market_entry_risk_report_filename() -> None:
    brief = {"id": "dbf-entry", "title": "Market Entry API"}
    assert (
        market_entry_risk_report_filename(brief)
        == "dbf-entry-Market-Entry-API-market-entry-risk.md"
    )
    assert (
        market_entry_risk_report_filename(brief, fmt="json")
        == "dbf-entry-Market-Entry-API-market-entry-risk.json"
    )
    assert (
        market_entry_risk_report_filename(brief, fmt="csv")
        == "dbf-entry-Market-Entry-API-market-entry-risk.csv"
    )


def _store_with_market_entry_brief(tmp_path, profile: str) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_market_entry_risk_{profile}.db"),
        wal_mode=True,
    )
    if profile == "high":
        lead = BuildableUnit(
            id="bu-market-entry-high",
            title="Enterprise Workflow Entry",
            one_liner="Replace manual enterprise compliance handoffs.",
            category="application",
            problem="Enterprise teams rely on incumbent platforms and manual approval workflows.",
            solution="Coordinate migration, integration, security review, and compliance launch gates.",
            value_proposition="Reduce approval delays for regulated enterprise teams.",
            specific_user="operations manager",
            buyer="enterprise IT director",
            workflow_context="procurement and security approval workflow",
            current_workaround="manual handoffs inside an incumbent suite",
            why_now="A regulatory deadline and budget cycle create urgent launch pressure now.",
            validation_plan="Interview security reviewers after procurement approval.",
            first_10_customers="enterprise buyers reached through direct sales",
            domain_risks=[
                "Incumbent suite vendors may copy the workflow.",
                "Compliance and security review can block adoption.",
                "Migration and integration switching costs may be high.",
            ],
            evidence_signals=[],
            inspiring_insights=[],
            domain="enterprise",
            status="candidate",
        )
        readiness_score = 41.0
        design_status = "candidate"
        risks = [
            "Competition from incumbent platforms is likely.",
            "Compliance constraints may delay market entry.",
        ]
        title = "High Market Entry Brief"
    elif profile == "low":
        lead = BuildableUnit(
            id="bu-market-entry-low",
            title="Self Serve Team Rituals",
            one_liner="A self-serve weekly ritual helper.",
            category="application",
            problem="Small teams need lightweight recurring retros without changing tools.",
            solution="Generate a weekly recap inside the existing workflow with no migration.",
            value_proposition="Save time with a low-friction pilot and recurring weekly habit.",
            specific_user="team lead",
            buyer="head of product",
            workflow_context="existing weekly planning workflow",
            current_workaround="lightweight notes",
            why_now="Teams already run weekly planning and want a self-serve improvement.",
            validation_plan="Run a self-serve pilot with five teams and measure weekly reuse.",
            first_10_customers="product communities and existing customer referrals",
            domain_risks=["Public data and no PII keep compliance review light."],
            evidence_signals=["sig-weekly"],
            inspiring_insights=["ins-weekly"],
            domain="productivity",
            status="approved",
        )
        readiness_score = 88.0
        design_status = "approved"
        risks: list[str] = []
        title = "Low Market Entry Brief"
    else:
        lead = BuildableUnit(
            id="bu-market-entry-sparse",
            title="Sparse Market Entry Lead",
            one_liner="Sparse source for deterministic fallback behavior.",
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
        readiness_score = 20.0
        design_status = "draft"
        risks = []
        title = "Sparse Market Entry Brief"

    store.insert_buildable_unit(lead)
    if profile == "high":
        store.insert_prior_art_match(
            lead.id,
            {
                "source": "market",
                "title": "Enterprise Workflow Suite",
                "url": "https://example.com/suite",
                "description": "Incumbent enterprise platform for compliance workflow approvals.",
                "relevance_score": 0.9,
            },
        )

    brief_id = store.insert_design_brief(
        ProjectBrief(
            title=title,
            domain=lead.domain,
            theme="market-entry",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=readiness_score,
            why_this_now=lead.why_now,
            merged_product_concept=lead.solution,
            synthesis_rationale=lead.value_proposition,
            mvp_scope=["Market entry risk report"] if profile != "sparse" else [],
            first_milestones=["Validate channel"] if profile != "sparse" else [],
            validation_plan=lead.validation_plan,
            risks=risks,
            source_idea_ids=[lead.id],
            design_status=design_status,
        )
    )
    return store, brief_id
