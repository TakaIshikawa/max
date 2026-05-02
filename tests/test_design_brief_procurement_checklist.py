"""Tests for design brief procurement checklist generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_procurement_checklist import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_procurement_checklist,
    procurement_checklist_filename,
    render_design_brief_procurement_checklist,
    render_procurement_checklist_csv,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_procurement_checklist_sections_and_items(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_procurement_checklist(store, brief_id)
        repeated = build_design_brief_procurement_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist == repeated
    assert checklist is not None
    assert checklist["schema_version"] == SCHEMA_VERSION
    assert checklist["kind"] == "max.design_brief.procurement_checklist"
    assert checklist["design_brief"]["id"] == brief_id
    assert checklist["design_brief"]["buyer"] == "VP of Operations"
    assert checklist["summary"]["procurement_gate"] == "ready_for_procurement_review"
    assert checklist["missing_inputs"] == []
    assert [section["id"] for section in checklist["sections"]] == [
        "security_review",
        "legal_privacy",
        "budget_owner",
        "vendor_evaluation",
        "implementation_owner",
        "approval_gates",
    ]
    assert [item["id"] for item in checklist["checklist_items"]] == [
        f"DBPC{index}" for index in range(1, 13)
    ]
    assert all(item["owner_role"] for item in checklist["checklist_items"])
    assert all(item["rationale"] for item in checklist["checklist_items"])
    assert all(item["source_fields"] for item in checklist["checklist_items"])
    assert all(item["completion_evidence"] for item in checklist["checklist_items"])
    assert [gate["name"] for gate in checklist["approval_gates"]] == [
        "Security review",
        "Legal / privacy review",
        "Budget approval",
        "Implementation approval",
    ]
    assert json.loads(json.dumps(checklist))["design_brief"]["id"] == brief_id


def test_build_design_brief_procurement_checklist_sparse_brief_surfaces_missing_inputs(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        checklist = build_design_brief_procurement_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    assert checklist["summary"]["procurement_gate"] == "needs_procurement_inputs"
    missing_fields = [item["field"] for item in checklist["missing_inputs"]]
    assert missing_fields == [
        "buyer",
        "risks",
        "pricing_strategy",
        "market_sizing_hints",
        "support_needs",
        "validation_plan",
    ]
    assert any("fallback risk review" in item["fallback"] for item in checklist["missing_inputs"])
    assert checklist["approval_gates"][-1]["name"] == "Missing input resolution"
    fallback_item = checklist["checklist_items"][-1]
    assert fallback_item["task"].startswith("Block expansion until missing procurement inputs")
    assert "pricing_strategy" in fallback_item["source_fields"]


def test_render_design_brief_procurement_checklist_markdown_json_and_invalid_format(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_procurement_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    markdown = render_design_brief_procurement_checklist(checklist)
    assert markdown.startswith("# Procurement Checklist: Procurement Checklist Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Security Review" in markdown
    assert "## Legal / Privacy" in markdown
    assert "## Budget Owner" in markdown
    assert "## Vendor Evaluation" in markdown
    assert "## Implementation Owner" in markdown
    assert "## Approval Gates" in markdown
    assert "### DBPC1: Prepare security questionnaire inputs" in markdown
    assert "- Owner role: Security owner" in markdown
    assert "- Source fields: tech_approach, suggested_stack, merged_product_concept" in markdown
    assert "- Completion evidence: Completed security questionnaire notes" in markdown
    assert "## Recommended Next Actions" in markdown

    parsed = json.loads(render_design_brief_procurement_checklist(checklist, fmt="json"))
    assert parsed == checklist

    with pytest.raises(ValueError, match="Unsupported procurement checklist format: yaml"):
        render_design_brief_procurement_checklist(checklist, fmt="yaml")


def test_render_procurement_checklist_csv_headers_ordering_and_fields(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_procurement_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    csv_output = render_procurement_checklist_csv(checklist)
    assert csv_output == render_design_brief_procurement_checklist(checklist, fmt="csv")
    reader = csv.DictReader(io.StringIO(csv_output))
    rows = list(reader)

    assert reader.fieldnames == list(CSV_COLUMNS)
    assert csv_output.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert [row["requirement"] for row in rows] == [item["task"] for item in checklist["checklist_items"]]

    first = rows[0]
    assert first["category"] == "Security Review"
    assert first["requirement"] == (
        "Prepare security questionnaire inputs for architecture, access, and data boundaries."
    )
    assert first["priority"] == ""
    assert first["owner"] == "Security owner"
    assert first["vendor_evidence"] == "Completed security questionnaire notes or not-applicable decision."
    assert first["approval_gate"] == "Security review"
    assert first["due_timing"] == ""
    assert first["notes"] == (
        "FastAPI and persisted checklist generation with audit-friendly JSON.; "
        "language: python; framework: fastapi"
    )


def test_render_procurement_checklist_csv_escapes_commas_newlines_and_optional_fields() -> None:
    report = {
        "design_brief": {"id": "dbf-csv"},
        "approval_gates": [
            {"name": "Budget approval", "owner_role": "Revenue, Ops"},
            {"name": "Security review", "owner_role": "Security owner"},
        ],
        "checklist_items": [
            {
                "id": "DBPC2",
                "section_id": "budget_owner",
                "section_title": "Budget Owner",
                "category": "Commercial, buyer enablement",
                "requirement": "Confirm signer,\nand budget path",
                "priority": "high",
                "owner": "Revenue, Ops",
                "vendor_evidence": ["quote, signed", "approval\nmemo"],
                "due_timing": "Before vendor review",
                "source_fields": ["buyer", "pricing_strategy"],
                "source_idea_ids": ["bu-2", "bu-1"],
                "notes": "Needs buyer-ready, spreadsheet-safe output.",
            },
            {
                "id": "DBPC1",
                "section_id": "security_review",
                "section_title": "Security Review",
                "task": "Prepare packet",
            },
        ],
    }

    csv_output = render_procurement_checklist_csv(report)
    reader = csv.DictReader(io.StringIO(csv_output))
    rows = list(reader)

    assert [row["requirement"] for row in rows] == [
        "Confirm signer,\nand budget path",
        "Prepare packet",
    ]
    assert rows[0]["category"] == "Commercial, buyer enablement"
    assert rows[0]["requirement"] == "Confirm signer,\nand budget path"
    assert rows[0]["priority"] == "high"
    assert rows[0]["owner"] == "Revenue, Ops"
    assert rows[0]["vendor_evidence"] == "quote, signed; approval\nmemo"
    assert rows[0]["approval_gate"] == "Budget approval"
    assert rows[0]["due_timing"] == "Before vendor review"
    assert rows[0]["notes"] == "Needs buyer-ready, spreadsheet-safe output."
    assert rows[1]["priority"] == ""
    assert rows[1]["owner"] == ""
    assert rows[1]["vendor_evidence"] == ""
    assert rows[1]["approval_gate"] == ""
    assert rows[1]["due_timing"] == ""
    assert rows[1]["notes"] == ""
    assert "{'" not in csv_output
    assert '"Confirm signer,\nand budget path"' in csv_output


def test_render_procurement_checklist_csv_empty_checklist_has_header_only() -> None:
    report = {"design_brief": {"id": "dbf-empty"}, "checklist_items": []}

    csv_output = render_procurement_checklist_csv(report)

    assert csv_output == ",".join(CSV_COLUMNS) + "\n"
    assert list(csv.DictReader(io.StringIO(csv_output))) == []


def test_build_design_brief_procurement_checklist_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_procurement_checklist.db"), wal_mode=True)
    try:
        checklist = build_design_brief_procurement_checklist(store, "dbf-missing")
    finally:
        store.close()

    assert checklist is None


def test_procurement_checklist_filename_uses_brief_id_and_title() -> None:
    assert (
        procurement_checklist_filename(
            {"id": "dbf-test001", "title": "Procurement Checklist API Brief"},
            fmt="markdown",
        )
        == "dbf-test001-Procurement-Checklist-API-Brief-procurement-checklist.md"
    )
    assert (
        procurement_checklist_filename(
            {"id": "dbf-test001", "title": "Procurement Checklist API Brief"},
            fmt="json",
        )
        == "dbf-test001-Procurement-Checklist-API-Brief-procurement-checklist.json"
    )
    assert (
        procurement_checklist_filename(
            {"id": "dbf-test001", "title": "Procurement Checklist API Brief"},
            fmt="csv",
        )
        == "dbf-test001-Procurement-Checklist-API-Brief-procurement-checklist.csv"
    )


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_procurement_checklist_{sparse}.db"),
        wal_mode=True,
    )
    if sparse:
        lead = BuildableUnit(
            id="bu-procurement-sparse-lead",
            title="Sparse Procurement Lead",
            one_liner="Generate sparse procurement checklists.",
            category="application",
            problem="Procurement handoffs need explicit gaps.",
            solution="Build procurement readiness fallbacks.",
            value_proposition="",
            specific_user="",
            buyer="",
            workflow_context="",
            current_workaround="",
            validation_plan="",
            first_10_customers="",
            domain_risks=[],
            evidence_signals=[],
            inspiring_insights=[],
            tech_approach="",
            suggested_stack={},
            domain="developer-tools",
            status="approved",
        )
        risks: list[str] = []
        validation_plan = ""
    else:
        lead = BuildableUnit(
            id="bu-procurement-lead",
            title="Procurement Checklist Lead",
            one_liner="Prepare procurement handoffs from design briefs.",
            category="application",
            problem="Enterprise buyers need procurement artifacts before adoption.",
            solution="Export deterministic procurement checklists from persisted design briefs.",
            value_proposition="Reduce approval friction for organizational buyers.",
            specific_user="operations manager",
            buyer="VP of Operations",
            workflow_context="enterprise workflow rollout with customer data",
            current_workaround="manual vendor review documents",
            why_now="Generated ideas increasingly target organizational buyers.",
            validation_plan="Run procurement review with two pilot buyers.",
            first_10_customers="mid-market operations teams with formal procurement",
            domain_risks=[
                "Security and privacy review may delay customer data access.",
                "Budget owner may differ from the workflow sponsor.",
            ],
            evidence_rationale="Signals show budget, compliance, and procurement readiness gaps.",
            evidence_signals=["sig-procurement-budget", "sig-procurement-market"],
            inspiring_insights=["ins-procurement"],
            tech_approach="FastAPI and persisted checklist generation with audit-friendly JSON.",
            suggested_stack={"language": "python", "framework": "fastapi"},
            domain="developer-tools",
            status="approved",
        )
        risks = ["Legal review is required before customer workflow data is used."]
        validation_plan = "Confirm procurement checklist traceability with budget owners."

    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Procurement Checklist Brief",
            domain="developer-tools",
            theme="procurement-readiness",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=86.0,
            why_this_now="Organizational buyers need procurement readiness before rollout.",
            merged_product_concept="A procurement checklist export for persisted design briefs.",
            synthesis_rationale="Connects buyer, budget, compliance, support, and validation readiness.",
            mvp_scope=["JSON procurement checklist", "Markdown procurement checklist"],
            first_milestones=["Return procurement checklist JSON"],
            validation_plan=validation_plan,
            risks=risks,
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
