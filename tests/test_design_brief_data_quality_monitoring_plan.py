from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_data_quality_monitoring_plan import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_data_quality_monitoring_plan,
    render_design_brief_data_quality_monitoring_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_data_quality_monitoring_plan_derives_checks_from_context(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_data_quality_monitoring_plan(store, brief_id)
        repeated = build_design_brief_data_quality_monitoring_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["workflow_context"] == "customer renewal scoring"
    assert report["summary"]["source_evidence_count"] == 4
    assert "customer renewal scoring" in report["critical_data_assumptions"][0]["action"]
    assert "Renewal score" in report["critical_data_assumptions"][1]["action"]
    assert report["anomaly_triggers"][1]["severity"] == "high"
    assert "privacy review" in report["remediation_actions"][2]["action"]


def test_sparse_data_quality_monitoring_plan_is_deterministic(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_data_quality_monitoring_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
    ]
    assert report["freshness_checks"][0]["action"] == (
        "Sparse Data Quality operating workflow monitoring updates within one business day."
    )
    assert report["quality_checks"][0]["severity"] == "high"


def test_data_quality_monitoring_plan_missing_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_data_quality_monitoring_plan(store, "missing") is None
    finally:
        store.close()


def test_render_data_quality_monitoring_plan_formats(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_data_quality_monitoring_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(render_design_brief_data_quality_monitoring_plan(report, "json")) == report
    markdown = render_design_brief_data_quality_monitoring_plan(report, "markdown")
    assert markdown.startswith("# Data Quality Monitoring Plan: Data Quality Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Freshness Checks" in markdown
    assert "## Remediation Actions" in markdown

    csv_text = render_design_brief_data_quality_monitoring_plan(report, "csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows[0]["design_brief_id"] == brief_id
    assert {row["section"] for row in rows} == set(
        (
            "critical_data_assumptions",
            "quality_checks",
            "freshness_checks",
            "anomaly_triggers",
            "ownership",
            "remediation_actions",
        )
    )

    with pytest.raises(ValueError, match="Unsupported data quality monitoring plan format"):
        render_design_brief_data_quality_monitoring_plan(report, "xml")


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"data_quality_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id=f"bu-data-quality-{sparse}",
        title="Data Quality Lead",
        one_liner="Monitor renewal data quality.",
        category="application",
        problem="Renewal teams distrust scoring data.",
        solution="A renewal quality monitor.",
        value_proposition="Make renewal reporting reliable.",
        specific_user="" if sparse else "revenue operations analyst",
        buyer="" if sparse else "chief revenue officer",
        workflow_context="" if sparse else "customer renewal scoring",
        validation_plan="Compare scores with renewal outcomes.",
        domain_risks=[] if sparse else ["Needs privacy review for customer health fields."],
        evidence_signals=["CRM exports", "support tickets"],
        inspiring_insights=["manual spreadsheets drift weekly"],
        domain="revops",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Data Quality Brief" if sparse else "Data Quality Brief",
            domain="revops",
            theme="monitoring",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=45.0 if sparse else 76.0,
            why_this_now="Renewal season is starting.",
            merged_product_concept="Renewal quality monitor",
            synthesis_rationale="Data checks are needed before reporting.",
            mvp_scope=[] if sparse else ["Renewal score", "Account health feed"],
            first_milestones=["Define checks"],
            validation_plan="" if sparse else "Compare scores with renewal outcomes.",
            risks=[] if sparse else ["Needs privacy review for customer health fields."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
