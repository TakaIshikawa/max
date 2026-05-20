from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_integration_cutover_plan import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_integration_cutover_plan,
    render_design_brief_integration_cutover_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_integration_cutover_plan_builds_deterministic_steps(tmp_path) -> None:
    store, brief_id, lead_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_integration_cutover_plan(store, brief_id)
        repeated = build_design_brief_integration_cutover_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["workflow_context"] == "Slack incident handoff"
    assert "Slack ticket sync" in report["summary"]["cutover_goal"]
    assert "Slack event relay" in report["cutover_prerequisites"][0]["action"]
    assert "security approval" in report["rollback_checkpoints"][1]["action"]
    for section in (
        "cutover_prerequisites",
        "cutover_sequence",
        "rollback_checkpoints",
        "partner_coordination",
        "verification_probes",
        "customer_communications",
    ):
        assert all(row["source_idea_id"] == lead_id for row in report[section])


def test_sparse_integration_cutover_plan_uses_fallbacks(tmp_path) -> None:
    store, brief_id, _lead_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_integration_cutover_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
    ]
    assert "Sparse Cutover operating workflow" in report["cutover_sequence"][2]["action"]
    assert report["cutover_sequence"][1]["severity"] == "high"


def test_integration_cutover_plan_missing_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_integration_cutover_plan(store, "missing") is None
    finally:
        store.close()


def test_render_integration_cutover_plan_formats(tmp_path) -> None:
    store, brief_id, _lead_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_integration_cutover_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(render_design_brief_integration_cutover_plan(report, "json")) == report
    markdown = render_design_brief_integration_cutover_plan(report, "markdown")
    assert markdown.startswith("# Integration Cutover Plan: Integration Cutover Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Rollback Checkpoints" in markdown
    assert "## Customer Communications" in markdown

    csv_text = render_design_brief_integration_cutover_plan(report, "csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows[0]["design_brief_id"] == brief_id
    assert rows[0]["source_idea_id"] == _lead_id

    with pytest.raises(ValueError, match="Unsupported integration cutover plan format"):
        render_design_brief_integration_cutover_plan(report, "html")


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str, str]:
    store = Store(db_path=str(tmp_path / f"cutover_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id=f"bu-cutover-{sparse}",
        title="Cutover Lead",
        one_liner="Plan integration cutovers.",
        category="application",
        problem="Integration launches lack rollback discipline.",
        solution="Slack ticket sync",
        value_proposition="Lower launch risk.",
        specific_user="" if sparse else "incident commander",
        buyer="" if sparse else "support VP",
        workflow_context="" if sparse else "Slack incident handoff",
        validation_plan="Run cutover rehearsal.",
        domain_risks=[] if sparse else ["Requires security approval before live customer messages."],
        evidence_signals=["Slack pilot request"],
        inspiring_insights=[],
        domain="support",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Cutover Brief" if sparse else "Integration Cutover Brief",
            domain="support",
            theme="integration",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=52.0 if sparse else 79.0,
            why_this_now="Customers want live handoff.",
            merged_product_concept="Slack ticket sync",
            synthesis_rationale="Cutover controls reduce launch risk.",
            mvp_scope=[] if sparse else ["Slack event relay", "Ticket creation"],
            first_milestones=["Rehearse"],
            validation_plan="Run cutover rehearsal.",
            risks=[] if sparse else ["Requires security approval before live customer messages."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id, lead.id
