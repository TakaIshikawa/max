from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_sla_definition_plan import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_sla_definition_plan,
    render_design_brief_sla_definition_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_sla_definition_plan_creates_deterministic_sections(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_sla_definition_plan(store, brief_id)
        repeated = build_design_brief_sla_definition_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["severity_recommendation"] == "high"
    assert report["summary"]["first_response_threshold"] == "1 business hour"
    assert "billing reconciliation" in report["service_promises"][0]["action"]
    assert "99.5%" in report["measurable_indicators"][0]["evidence"]
    assert "Payment matching" in report["exclusions"][0]["evidence"]
    assert "data latency" in report["escalation_thresholds"][1]["action"]
    assert report["customer_facing_wording"][0]["action"].startswith("We support")


def test_sla_definition_plan_readiness_influences_thresholds(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_sla_definition_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["severity_recommendation"] == "high"
    assert report["service_promises"][0]["evidence"] == "Target availability 99.5%."
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
    ]


def test_sla_definition_plan_missing_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_sla_definition_plan(store, "missing") is None
    finally:
        store.close()


def test_render_sla_definition_plan_formats(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_sla_definition_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(render_design_brief_sla_definition_plan(report, "json")) == report
    markdown = render_design_brief_sla_definition_plan(report, "markdown")
    assert markdown.startswith("# SLA Definition Plan: SLA Definition Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Escalation Thresholds" in markdown
    assert "## Customer-Facing Wording" in markdown

    csv_text = render_design_brief_sla_definition_plan(report, "csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows[0]["design_brief_id"] == brief_id
    assert {row["section"] for row in rows} == set(
        (
            "service_promises",
            "measurable_indicators",
            "exclusions",
            "escalation_thresholds",
            "review_cadence",
            "customer_facing_wording",
        )
    )

    with pytest.raises(ValueError, match="Unsupported SLA definition plan format"):
        render_design_brief_sla_definition_plan(report, "toml")


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"sla_definition_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id=f"bu-sla-{sparse}",
        title="SLA Lead",
        one_liner="Define customer SLAs.",
        category="application",
        problem="Customers need service promises.",
        solution="Billing reliability monitor",
        value_proposition="Set clear expectations.",
        specific_user="" if sparse else "billing operations manager",
        buyer="" if sparse else "finance VP",
        workflow_context="" if sparse else "billing reconciliation",
        validation_plan="Measure reconciliation response time.",
        domain_risks=[] if sparse else ["Customer reports are sensitive to data latency."],
        evidence_signals=["billing team interviews"],
        inspiring_insights=[],
        domain="finance",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse SLA Brief" if sparse else "SLA Definition Brief",
            domain="finance",
            theme="sla",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=50.0 if sparse else 84.0,
            why_this_now="Finance team is adopting automation.",
            merged_product_concept="Billing reliability monitor",
            synthesis_rationale="SLA wording aligns support and customer expectations.",
            mvp_scope=[] if sparse else ["Payment matching", "Exception queue"],
            first_milestones=["Define thresholds"],
            validation_plan="Measure reconciliation response time.",
            risks=[] if sparse else ["Customer reports are sensitive to data latency."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
