from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_operational_acceptance_plan import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_operational_acceptance_plan,
    render_design_brief_operational_acceptance_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_operational_acceptance_plan_creates_required_gates(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_operational_acceptance_plan(store, brief_id)
        repeated = build_design_brief_operational_acceptance_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["workflow_context"] == "audit evidence collection"
    assert "Compliance evidence portal" in report["summary"]["acceptance_goal"]
    assert report["supportability_gates"][0]["name"] == "Support playbook ready"
    assert "audit evidence collection" in report["observability_gates"][0]["action"]
    assert report["security_handoff_gates"][0]["severity"] == "high"
    assert report["documentation_gates"][0]["owner"] == "Documentation owner"
    assert report["launch_ownership_gates"][0]["owner"] == "compliance VP"
    assert "customer evidence" in report["risk_exception_gates"][0]["action"]


def test_low_readiness_operational_acceptance_plan_warns(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_operational_acceptance_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["readiness_warning"] == (
        "Readiness below 50 requires executive launch exception."
    )
    assert report["risk_exception_gates"][1]["severity"] == "high"
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
    ]


def test_operational_acceptance_plan_missing_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_operational_acceptance_plan(store, "missing") is None
    finally:
        store.close()


def test_render_operational_acceptance_plan_formats(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_operational_acceptance_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(render_design_brief_operational_acceptance_plan(report, "json")) == report
    markdown = render_design_brief_operational_acceptance_plan(report, "markdown")
    assert markdown.startswith("# Operational Acceptance Plan: Operational Acceptance Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Security Handoff Gates" in markdown
    assert "## Risk Exception Gates" in markdown

    csv_text = render_design_brief_operational_acceptance_plan(report, "csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows[0]["design_brief_id"] == brief_id
    assert {row["section"] for row in rows} == set(
        (
            "supportability_gates",
            "observability_gates",
            "security_handoff_gates",
            "documentation_gates",
            "launch_ownership_gates",
            "risk_exception_gates",
        )
    )

    with pytest.raises(ValueError, match="Unsupported operational acceptance plan format"):
        render_design_brief_operational_acceptance_plan(report, "yaml")


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"operational_acceptance_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id=f"bu-operational-acceptance-{sparse}",
        title="Operational Acceptance Lead",
        one_liner="Create launch gates.",
        category="application",
        problem="Teams launch without operational acceptance.",
        solution="Compliance evidence portal",
        value_proposition="Reduce launch handoff risk.",
        specific_user="" if sparse else "compliance operations lead",
        buyer="" if sparse else "compliance VP",
        workflow_context="" if sparse else "audit evidence collection",
        validation_plan="Run support and launch review.",
        domain_risks=[] if sparse else ["Security review needed before customer evidence upload."],
        evidence_signals=["support review notes"],
        inspiring_insights=[],
        domain="compliance",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Operational Acceptance Brief" if sparse else "Operational Acceptance Brief",
            domain="compliance",
            theme="operations",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=44.0 if sparse else 72.0,
            why_this_now="Launch ownership is unclear.",
            merged_product_concept="Compliance evidence portal",
            synthesis_rationale="Acceptance gates reduce handoff gaps.",
            mvp_scope=[] if sparse else ["Evidence upload", "Reviewer notes"],
            first_milestones=["Create gates"],
            validation_plan="Run support and launch review.",
            risks=[] if sparse else ["Security review needed before customer evidence upload."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
