"""Tests for design brief change impact memos."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_change_impact import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_change_impact_memo,
    render_design_brief_change_impact_memo,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_change_impact_memo_has_required_sections_and_renderers(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_change_impact_memo(store, brief_id, "Expand to regulated workflows")
        repeated = build_design_brief_change_impact_memo(store, brief_id, "Expand to regulated workflows")
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["impact_summary"]["proposed_change"] == "Expand to regulated workflows"
    assert report["impact_summary"]["impact_level"] == "high"
    assert set(report) == {
        "schema_version",
        "kind",
        "source",
        "design_brief",
        "impact_summary",
        "affected_stakeholders",
        "impacted_dependencies",
        "metric_risks",
        "sequencing_changes",
        "evidence_references",
    }
    assert report["affected_stakeholders"][0]["name"] == "VP of Operations"
    assert report["impacted_dependencies"][1]["name"] == "Validation plan"
    assert report["metric_risks"][0]["name"] == "Activation"
    assert report["sequencing_changes"][0]["name"] == "Change review"

    markdown = render_design_brief_change_impact_memo(report)
    assert markdown.startswith("# Change Impact Memo: Change Impact Brief")
    assert "## Metric Risks" in markdown
    assert json.loads(render_design_brief_change_impact_memo(report, fmt="json")) == report

    csv_text = render_design_brief_change_impact_memo(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(rows) == 10
    assert rows[0]["design_brief_id"] == brief_id
    assert rows[0]["section"] == "affected_stakeholders"


def test_change_impact_missing_brief_and_invalid_format(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_change.db"), wal_mode=True)
    try:
        assert build_design_brief_change_impact_memo(store, "dbf-missing") is None
    finally:
        store.close()

    with pytest.raises(ValueError, match="Unsupported change impact memo format: yaml"):
        render_design_brief_change_impact_memo({"design_brief": {}, "impact_summary": {}}, fmt="yaml")


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "change_impact.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-change-lead",
        title="Change Impact Lead",
        one_liner="Analyze design brief changes.",
        category="application",
        problem="Teams need impact analysis before scope changes.",
        solution="Generate deterministic impact memos.",
        value_proposition="Reduce scope-change risk.",
        specific_user="implementation manager",
        buyer="VP of Operations",
        workflow_context="enterprise rollout review",
        current_workaround="manual change notes",
        validation_plan="Run changed-scope pilot review.",
        domain_risks=["Privacy review may expand."],
        evidence_rationale="Signals show regulated workflow demand.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Change Impact Brief",
            domain="developer-tools",
            theme="scope",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=82.0,
            why_this_now="Scope is changing before pilot.",
            merged_product_concept="A deterministic change impact memo.",
            synthesis_rationale="Connects scope, dependency, risk, and sequencing impacts.",
            mvp_scope=["Markdown memo", "CSV memo"],
            first_milestones=["Approve changed scope", "Update validation"],
            validation_plan="Run changed-scope pilot review.",
            risks=["Privacy review may expand."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
