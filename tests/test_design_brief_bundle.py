"""Tests for consolidated design brief bundle exports."""

from __future__ import annotations

import json

from max.analysis import design_brief_bundle
from max.analysis.design_brief_bundle import (
    ARTIFACT_NAMES,
    SCHEMA_VERSION,
    build_design_brief_bundle,
    render_design_brief_bundle,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def test_build_design_brief_bundle_composes_supported_artifacts(tmp_path) -> None:
    store, brief_id = _store_with_design_brief(tmp_path)
    try:
        bundle = build_design_brief_bundle(store, brief_id)
    finally:
        store.close()

    assert bundle is not None
    assert bundle["schema_version"] == SCHEMA_VERSION
    assert bundle["design_brief"]["id"] == brief_id
    assert set(ARTIFACT_NAMES) <= set(bundle)
    assert set(ARTIFACT_NAMES) <= set(bundle["artifact_status"])
    assert bundle["artifact_status"]["design_brief"]["status"] == "generated"
    assert bundle["artifact_status"]["blueprint_source_brief"]["status"] == "generated"
    assert bundle["artifact_status"]["validation_plan"]["status"] == "generated"
    assert bundle["artifact_status"]["evidence_matrix"]["status"] == "generated"
    assert bundle["artifact_status"]["risk_register"]["status"] == "generated"
    assert bundle["artifact_status"]["roadmap"]["status"] == "generated"
    assert bundle["artifact_status"]["prd"]["status"] == "generated"
    assert bundle["artifact_status"]["market_sizing"]["status"] == "generated"
    assert bundle["artifact_status"]["competitive_landscape"]["status"] == "generated"
    assert bundle["blueprint_source_brief"]["design_brief"]["id"] == brief_id
    assert bundle["prd"]["sections"]["problem"]["content"]
    assert json.loads(render_design_brief_bundle(bundle, fmt="json"))["design_brief"]["id"] == brief_id


def test_render_design_brief_bundle_markdown_has_stable_sections(tmp_path) -> None:
    store, brief_id = _store_with_design_brief(tmp_path)
    try:
        bundle = build_design_brief_bundle(store, brief_id)
    finally:
        store.close()

    assert bundle is not None
    markdown = render_design_brief_bundle(bundle, fmt="markdown")

    assert markdown.startswith("# Design Brief Bundle: Bundle Export Brief")
    assert "## Artifact Status" in markdown
    assert "## Design Brief" in markdown
    assert "## Blueprint Source Brief" in markdown
    assert "## Validation Plan" in markdown
    assert "## Evidence Matrix" in markdown
    assert "## Risk Register" in markdown
    assert "## Roadmap" in markdown
    assert "## PRD" in markdown
    assert "## Market Sizing" in markdown
    assert "## Competitive Landscape" in markdown
    assert "- **Roadmap**: `generated`" in markdown


def test_build_design_brief_bundle_records_errored_optional_artifact(tmp_path, monkeypatch) -> None:
    store, brief_id = _store_with_design_brief(tmp_path)

    def broken_roadmap(store, brief_id):
        raise RuntimeError("roadmap unavailable")

    monkeypatch.setattr(design_brief_bundle, "build_design_brief_roadmap", broken_roadmap)
    try:
        bundle = build_design_brief_bundle(store, brief_id)
    finally:
        store.close()

    assert bundle is not None
    assert bundle["roadmap"] is None
    assert bundle["artifact_status"]["roadmap"]["status"] == "errored"
    assert "roadmap unavailable" in bundle["artifact_status"]["roadmap"]["error"]
    assert bundle["artifact_status"]["prd"]["status"] == "generated"


def test_build_design_brief_bundle_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_bundle.db"), wal_mode=True)
    try:
        assert build_design_brief_bundle(store, "dbf-missing") is None
    finally:
        store.close()


def _store_with_design_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_bundle.db"), wal_mode=True)
    brief_id = _seed_design_brief(store)
    return store, brief_id


def _seed_design_brief(store: Store) -> str:
    store.insert_signal(
        Signal(
            id="sig-bundle-problem",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Bundle export demand",
            content="Agents need one design brief handoff payload.",
            url="https://example.com/bundle",
            tags=["problem"],
            credibility=0.8,
            metadata={"signal_role": "problem"},
        )
    )
    lead = BuildableUnit(
        id="bu-bundle-lead",
        title="Bundle Lead",
        one_liner="One payload for design brief handoff",
        category="application",
        problem="Coding agents need multiple calls to assemble a brief.",
        solution="Expose one bundle endpoint with generated artifacts.",
        value_proposition="Reduce handoff errors for downstream agents.",
        specific_user="coding agent operator",
        buyer="product engineering lead",
        workflow_context="agent design brief execution",
        current_workaround="manual API fan-out",
        why_now="Design briefs and derived artifacts already exist.",
        validation_plan="Run the bundle through a coding-agent handoff.",
        first_10_customers="internal product engineering teams",
        domain_risks=["Optional artifacts may fail independently."],
        evidence_rationale="Source evidence shows handoff friction.",
        evidence_signals=["sig-bundle-problem"],
        tech_approach="FastAPI bundle route with deterministic renderers.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Bundle Export Brief",
            domain="developer-tools",
            theme="agent-handoff",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=84.0,
            why_this_now="Execution agents need fewer calls now.",
            merged_product_concept="A consolidated design brief bundle.",
            synthesis_rationale="Packages persisted brief data with derived artifacts.",
            mvp_scope=["JSON bundle endpoint", "Markdown bundle endpoint"],
            first_milestones=["Build bundle composer", "Expose REST routes"],
            validation_plan="Verify one request includes all supported artifacts.",
            risks=["Optional artifacts may fail independently."],
            source_idea_ids=[lead.id],
        )
    )
