"""Tests for design brief objection handling guides."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis import (
    build_design_brief_objection_handling_guide as exported_build,
    render_design_brief_objection_handling_guide as exported_render,
)
from max.analysis.design_brief_objection_handling import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_objection_handling_guide,
    render_design_brief_objection_handling_guide,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_objection_handling_high_readiness_groups_perspectives(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        first = build_design_brief_objection_handling_guide(store, brief_id)
        second = build_design_brief_objection_handling_guide(store, brief_id)
    finally:
        store.close()

    assert first == second
    assert first is not None
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.design_brief.objection_handling"
    assert first["design_brief"]["id"] == brief_id
    assert first["summary"]["evidence_posture"] == "high_readiness"
    assert [item["perspective"] for item in first["objections"]] == [
        "buyer",
        "user",
        "security",
        "procurement",
        "implementation",
        "pricing",
        "executive",
    ]
    buyer = first["objections"][0]
    assert "VP of Operations" in buyer["objection"]
    assert buyer["proof_points"][:2] == [
        "Run pilot with two implementation managers.",
        "Signals show repeatable buying committee friction.",
    ]
    assert buyer["evidence_gap"] == "No material gap; keep proof current during pilot."
    assert "design_brief.buyer" in buyer["evidence_refs"]


def test_objection_handling_low_evidence_uses_gaps(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_objection_handling_guide(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["buyer"] == "economic sponsor"
    assert report["summary"]["target_user"] == "primary user"
    assert report["summary"]["evidence_posture"] == "low_evidence"
    assert report["summary"]["fallbacks_used"] == [
        "buyer",
        "specific_user",
        "workflow_context",
        "validation_plan",
    ]
    assert all("current guide relies on brief assumptions" in item["evidence_gap"] for item in report["objections"])


def test_objection_handling_renderers_and_exports(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = exported_build(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_objection_handling_guide(report)
    assert markdown.startswith("# Objection Handling Guide: Objection Handling Brief")
    assert "### Security" in markdown
    assert "## Evidence References" in markdown
    assert json.loads(exported_render(report, fmt="json")) == report

    csv_text = render_design_brief_objection_handling_guide(report, fmt="csv")
    assert csv_text == render_design_brief_objection_handling_guide(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(rows) == 7
    assert rows[0]["design_brief_id"] == brief_id
    assert json.loads(rows[0]["proof_points"])[0] == "Run pilot with two implementation managers."

    with pytest.raises(ValueError, match="Unsupported objection handling guide format: yaml"):
        render_design_brief_objection_handling_guide(report, fmt="yaml")


def test_objection_handling_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_objection.db"), wal_mode=True)
    try:
        assert build_design_brief_objection_handling_guide(store, "dbf-missing") is None
    finally:
        store.close()


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"objection_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-objection-lead" if not sparse else "bu-objection-sparse",
        title="Objection Lead",
        one_liner="Guide objection handling.",
        category="application",
        problem="Teams need answers to launch objections.",
        solution="Generate deterministic objection guides.",
        value_proposition="" if sparse else "Reduce sales and approval friction.",
        specific_user="" if sparse else "implementation manager",
        buyer="" if sparse else "VP of Operations",
        workflow_context="" if sparse else "enterprise rollout review",
        current_workaround="manual notes",
        validation_plan="" if sparse else "Run pilot with two implementation managers.",
        first_10_customers="operations teams",
        domain_risks=[] if sparse else ["Security review can delay data access."],
        evidence_rationale="" if sparse else "Signals show repeatable buying committee friction.",
        evidence_signals=["sig-objection"] if not sparse else [],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Objection Handling Brief",
            domain="developer-tools",
            theme="approval",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=86.0 if not sparse else 35.0,
            why_this_now="Buyers need approval evidence.",
            merged_product_concept="A deterministic guide for common objections.",
            synthesis_rationale="Connects buyer, user, risk, and value evidence.",
            mvp_scope=[] if sparse else ["Markdown guide", "CSV guide"],
            first_milestones=[] if sparse else ["Run buyer review", "Confirm security owner"],
            validation_plan="" if sparse else "Run pilot with two implementation managers.",
            risks=[] if sparse else ["Security review can delay data access."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
