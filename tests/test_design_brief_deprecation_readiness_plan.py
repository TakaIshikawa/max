from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_deprecation_readiness_plan import (
    SCHEMA_VERSION,
    build_design_brief_deprecation_readiness_plan,
    deprecation_readiness_plan_filename,
    render_design_brief_deprecation_readiness_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_deprecation_readiness_plan_includes_required_sections_and_keyword_risks(tmp_path) -> None:
    store, brief_id = _store(tmp_path)
    try:
        report = build_design_brief_deprecation_readiness_plan(store, brief_id)
        repeated = build_design_brief_deprecation_readiness_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert report == repeated
    assert json.loads(json.dumps(report)) == report
    assert report["schema_version"] == SCHEMA_VERSION
    assert set(report) >= {
        "replacement_path",
        "impacted_users",
        "compatibility_risks",
        "migration_steps",
        "communication_checkpoints",
        "rollback_criteria",
        "evidence_references",
        "evidence_gaps",
    }
    assert {risk["keyword"] for risk in report["compatibility_risks"]} >= {
        "legacy",
        "migration",
        "api",
        "integration",
        "customer",
        "rollback",
    }
    assert any(risk["severity"] == "high" for risk in report["compatibility_risks"])


def test_deprecation_readiness_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing.db"), wal_mode=True)
    try:
        assert build_design_brief_deprecation_readiness_plan(store, "missing") is None
    finally:
        store.close()


def test_deprecation_readiness_plan_sparse_brief_reports_gaps(tmp_path) -> None:
    store, brief_id = _store(tmp_path, sparse=True)
    try:
        report = build_design_brief_deprecation_readiness_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert [gap["id"] for gap in report["evidence_gaps"]] == [
        "missing_impacted_users",
        "missing_replacement_scope",
        "missing_migration_validation",
    ]


def test_deprecation_readiness_plan_renderers_and_filename(tmp_path) -> None:
    store, brief_id = _store(tmp_path)
    try:
        report = build_design_brief_deprecation_readiness_plan(store, brief_id)
    finally:
        store.close()
    assert report is not None
    assert json.loads(render_design_brief_deprecation_readiness_plan(report, "json")) == report
    markdown = render_design_brief_deprecation_readiness_plan(report)
    assert markdown.startswith("# Deprecation Readiness Plan: Deprecation Readiness Brief")
    assert "## Compatibility Risks" in markdown
    assert deprecation_readiness_plan_filename(report["design_brief"]) == f"{brief_id}-Deprecation-Readiness-Brief-deprecation-readiness-plan.md"
    with pytest.raises(ValueError, match="Unsupported deprecation readiness plan format"):
        render_design_brief_deprecation_readiness_plan(report, "yaml")


def _store(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"deprecation_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-deprecation-lead",
        title="Deprecation Lead",
        one_liner="Replace a legacy customer API.",
        category="platform",
        problem="Customers rely on a legacy API integration that needs migration and rollback coverage.",
        solution="Provide a replacement integration path with customer communication.",
        value_proposition="Reduce risk from legacy API deprecation.",
        specific_user="" if sparse else "integration admin",
        buyer="" if sparse else "VP Platform",
        workflow_context="" if sparse else "customer API integration workflow",
        validation_plan="" if sparse else "Validate migration and rollback with two customer sandboxes.",
        domain_risks=[] if sparse else ["Legacy API integration migration needs customer rollback plan."],
        evidence_signals=[] if sparse else ["customer migration request", "integration inventory"],
        domain="platform",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Deprecation Brief" if sparse else "Deprecation Readiness Brief",
            domain="platform",
            theme="deprecation",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=22.0 if sparse else 76.0,
            why_this_now="Legacy customer API support blocks platform cleanup.",
            merged_product_concept="Migrate customers from legacy API to the replacement integration.",
            synthesis_rationale="Pairs customer communication with integration migration and rollback.",
            mvp_scope=[] if sparse else ["Inventory API users", "Migrate sandbox integration"],
            first_milestones=[] if sparse else ["Publish notice", "Run rollback rehearsal"],
            validation_plan="" if sparse else "Validate migration and rollback with two customer sandboxes.",
            risks=[] if sparse else ["Legacy API integration migration needs customer rollback plan."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
