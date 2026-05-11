"""Tests for design brief operational dependency maps."""

from __future__ import annotations

import csv
import io
import json

from max.analysis import (
    build_design_brief_operational_dependency_map as exported_build,
    render_design_brief_operational_dependency_map as exported_render,
)
from max.analysis.design_brief_operational_dependency_map import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_operational_dependency_map,
    render_design_brief_operational_dependency_map,
    render_design_brief_operational_dependency_map_csv,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_operational_dependency_map_shape_and_renderers(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_operational_dependency_map(store, brief_id)
        missing = build_design_brief_operational_dependency_map(store, "missing")
    finally:
        store.close()

    assert missing is None
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.design_brief.operational_dependency_map"
    assert set(report) == {
        "schema_version",
        "kind",
        "source",
        "design_brief",
        "summary",
        "dependency_groups",
        "owner_handoffs",
        "external_systems",
        "risk_links",
        "checkpoint_links",
        "evidence_references",
    }
    assert report["design_brief"]["source_idea_ids"] == ["bu-dep-lead"]
    assert report["summary"]["external_system_count"] == 2
    assert [item["id"] for item in report["checkpoint_links"]] == ["CHK1", "CHK2"]

    markdown = render_design_brief_operational_dependency_map(report)
    rendered_json = render_design_brief_operational_dependency_map(report, fmt="json")
    csv_text = render_design_brief_operational_dependency_map_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert markdown.startswith("# Operational Dependency Map: Dependency Brief")
    assert "## Owner Handoffs" in markdown
    assert json.loads(rendered_json)["design_brief"]["id"] == brief_id
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert any(row["section"] == "external_systems" and row["name"] == "Slack" for row in rows)


def test_operational_dependency_map_exports(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = exported_build(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert json.loads(exported_render(report, fmt="json"))["schema_version"] == SCHEMA_VERSION


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "dependency_map.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-dep-lead",
        title="Dependency Lead",
        one_liner="Map operational dependencies.",
        category="application",
        problem="Launch teams lack dependency visibility.",
        solution="Slack and GitHub integration dependency map.",
        value_proposition="Reduce launch handoff misses.",
        specific_user="launch manager",
        buyer="VP Operations",
        workflow_context="launch dependency review",
        current_workaround="manual spreadsheet",
        validation_plan="Review map with launch and support owners.",
        first_10_customers="ops teams",
        domain_risks=["Support ownership unclear."],
        evidence_signals=["sig-dep"],
        inspiring_insights=[],
        tech_approach="Slack and GitHub integration workflow.",
        suggested_stack={"collaboration": "Slack", "source": "GitHub"},
        composability_notes="",
        domain="ops",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Dependency Brief",
            domain="ops",
            theme="launch-ops",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=82.0,
            why_this_now="Operational launches need explicit dependency maps.",
            merged_product_concept="Slack and GitHub operational launch workflow.",
            synthesis_rationale="Map owners, risks, systems, and checkpoints.",
            mvp_scope=["dependency map"],
            first_milestones=["render CSV"],
            validation_plan="Review map with launch and support owners.",
            risks=["Support ownership unclear."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
