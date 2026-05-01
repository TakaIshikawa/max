"""Tests for design brief sales enablement checklist generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_sales_enablement_checklist import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_sales_enablement_checklist,
    render_design_brief_sales_enablement_checklist,
    sales_enablement_checklist_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_sales_enablement_checklist_complete_brief(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_sales_enablement_checklist(store, brief_id)
        repeated = build_design_brief_sales_enablement_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    assert checklist == repeated
    assert checklist["schema_version"] == SCHEMA_VERSION
    assert checklist["kind"] == KIND
    assert checklist["design_brief"]["id"] == brief_id
    assert checklist["summary"]["target_buyer"] == "VP of Revenue Operations"
    assert checklist["summary"]["target_user"] == "sales engineer"
    assert checklist["summary"]["workflow_context"] == "pre-demo qualification and handoff"
    assert checklist["summary"]["sales_readiness_gate"] == "ready_for_seller_use"
    assert checklist["summary"]["fallbacks_used"] == []
    assert checklist["missing_evidence_actions"] == []
    assert [section["id"] for section in checklist["sections"]] == [
        "qualification",
        "discovery",
        "proof",
        "demo_readiness",
        "objection_handling",
        "handoff",
    ]
    assert [item["id"] for item in checklist["checklist_items"]] == [
        f"DBSE{index}" for index in range(1, 13)
    ]
    assert all(item["owner_role"] for item in checklist["checklist_items"])
    assert all(item["rationale"] for item in checklist["checklist_items"])
    assert all(item["completion_evidence"] for item in checklist["checklist_items"])
    assert checklist["qualification_signals"][0]["signal"].startswith("Prospect owns")
    assert checklist["discovery_questions"][0]["question"].startswith("How does sales engineer")
    assert checklist["proof_points"][2]["evidence"] == "Run three pilot demos and compare handoff quality."
    assert checklist["demo_prep"][1]["prep"] == "Qualification scorecard"
    assert checklist["objection_handling_assets"][0]["objection"] == (
        "We can keep using the current workaround."
    )
    assert checklist["handoff_criteria"][2]["handoff_evidence"] == (
        "Run three pilot demos and compare handoff quality."
    )
    assert json.loads(json.dumps(checklist))["design_brief"]["id"] == brief_id


def test_build_design_brief_sales_enablement_checklist_sparse_brief_surfaces_missing_evidence(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        checklist = build_design_brief_sales_enablement_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    assert checklist["summary"]["sales_readiness_gate"] == "needs_sales_evidence"
    assert checklist["summary"]["fallbacks_used"] == [
        "buyer",
        "workflow_context",
        "value_proposition",
        "current_workaround",
    ]
    missing_fields = [item["field"] for item in checklist["missing_evidence_actions"]]
    assert missing_fields == [
        "buyer",
        "target_buyer",
        "qualification_signals",
        "discovery_questions",
        "proof_points",
        "demo_prep",
        "handoff_criteria",
    ]
    assert checklist["checklist_items"][-1]["task"].startswith("Resolve or explicitly accept")
    assert "buyer" in checklist["checklist_items"][-1]["rationale"]


def test_render_design_brief_sales_enablement_checklist_markdown_json_and_invalid_format(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        checklist = build_design_brief_sales_enablement_checklist(store, brief_id)
    finally:
        store.close()

    assert checklist is not None
    markdown = render_design_brief_sales_enablement_checklist(checklist)
    assert markdown.startswith("# Sales Enablement Checklist: Sales Enablement Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Qualification" in markdown
    assert "## Discovery" in markdown
    assert "## Proof" in markdown
    assert "## Demo Readiness" in markdown
    assert "## Objection Handling" in markdown
    assert "## Handoff" in markdown
    assert "### DBSE1: Confirm the prospect matches target buyer and workflow fit." in markdown
    assert "- Owner role: Account executive" in markdown
    assert "## Missing Evidence Actions" in markdown

    parsed = json.loads(render_design_brief_sales_enablement_checklist(checklist, fmt="json"))
    assert parsed == checklist

    with pytest.raises(ValueError, match="Unsupported sales enablement checklist format: yaml"):
        render_design_brief_sales_enablement_checklist(checklist, fmt="yaml")


def test_build_design_brief_sales_enablement_checklist_missing_brief_returns_none(
    tmp_path,
) -> None:
    store = Store(db_path=str(tmp_path / "missing_sales_enablement.db"), wal_mode=True)
    try:
        checklist = build_design_brief_sales_enablement_checklist(store, "dbf-missing")
    finally:
        store.close()

    assert checklist is None


def test_sales_enablement_checklist_filename_uses_brief_id_and_title() -> None:
    assert (
        sales_enablement_checklist_filename(
            {"id": "dbf-test001", "title": "Sales Enablement API Brief"},
            fmt="markdown",
        )
        == "dbf-test001-Sales-Enablement-API-Brief-sales-enablement-checklist.md"
    )
    assert (
        sales_enablement_checklist_filename(
            {"id": "dbf-test001", "title": "Sales Enablement API Brief"},
            fmt="json",
        )
        == "dbf-test001-Sales-Enablement-API-Brief-sales-enablement-checklist.json"
    )


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(
        db_path=str(tmp_path / f"design_brief_sales_enablement_{sparse}.db"),
        wal_mode=True,
    )
    if sparse:
        lead = BuildableUnit(
            id="bu-sales-enable-sparse",
            title="Sparse Sales Enablement Lead",
            one_liner="Sparse source for seller checklist fallbacks.",
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
    else:
        lead = BuildableUnit(
            id="bu-sales-enable-lead",
            title="Sales Enablement Lead",
            one_liner="Prepare sales engineers for demos and handoffs.",
            category="application",
            problem="Sellers lack a structured way to qualify prospects before demos.",
            solution="Generate a deterministic checklist for qualification, demo prep, and handoff.",
            value_proposition="Increase qualified demos and reduce post-demo handoff gaps.",
            specific_user="sales engineer",
            buyer="VP of Revenue Operations",
            workflow_context="pre-demo qualification and handoff",
            current_workaround="spreadsheet qualification notes and ad hoc demo prep",
            why_now="Sales teams are creating battlecards but still miss operational prep.",
            validation_plan="Run three pilot demos and compare handoff quality.",
            first_10_customers="B2B SaaS revenue teams with technical demos",
            domain_risks=["Prospects may object that demo prep adds sales cycle friction."],
            evidence_rationale="Seller interviews show inconsistent qualification and proof capture.",
            evidence_signals=["sig-demo-quality", "sig-handoff-gap"],
            inspiring_insights=["ins-sales-handoff"],
            tech_approach="FastAPI artifact export with deterministic JSON and Markdown.",
            suggested_stack={"backend": "FastAPI", "storage": "SQLite"},
            domain="sales",
            status="approved",
        )
        validation_plan = "Run three pilot demos and compare handoff quality."
        risks = ["Demo proof may not cover procurement or implementation concerns."]
        mvp_scope = ["Qualification scorecard", "Demo prep checklist"]
        first_milestones = ["Export checklist JSON"]

    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sales Enablement Brief",
            domain="sales",
            theme="sales-readiness",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=88.0 if not sparse else 32.0,
            why_this_now="Sales teams need operational prep before demos." if not sparse else "",
            merged_product_concept=(
                "A deterministic checklist for sales enablement and customer handoff."
                if not sparse
                else ""
            ),
            synthesis_rationale=(
                "Connects buyer, qualification, proof, demo readiness, objections, and handoff."
                if not sparse
                else ""
            ),
            mvp_scope=mvp_scope,
            first_milestones=first_milestones,
            validation_plan=validation_plan,
            risks=risks,
            source_idea_ids=[lead.id],
            design_status="approved" if not sparse else "draft",
        )
    )
    return store, brief_id
