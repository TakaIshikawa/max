"""Tests for design brief release notes generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_release_notes import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_release_notes,
    release_notes_filename,
    render_design_brief_release_notes,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def test_build_design_brief_release_notes_complete_brief_is_deterministic(tmp_path) -> None:
    store, brief_id = _store_with_complete_brief(tmp_path)
    try:
        report = build_design_brief_release_notes(store, brief_id)
        repeated = build_design_brief_release_notes(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["source_idea_ids"] == ["bu-release-lead", "bu-release-support"]
    assert report["summary"]["headline"] == "Release Notes Brief is ready for platform operator"
    assert report["summary"]["target_user"] == "platform operator"
    assert report["summary"]["buyer"] == "engineering director"
    assert report["summary"]["release_stage"] == "ready_for_customer_rollout"
    assert report["summary"]["fallbacks_used"] == []
    assert [item["id"] for item in report["customer_facing"]["shipped_capabilities"]] == [
        "CAP1",
        "CAP2",
    ]
    assert [item["id"] for item in report["customer_facing"]["target_users"]] == [
        "primary_user",
        "release_sponsor",
    ]
    assert [item["id"] for item in report["customer_facing"]["rollout_notes"]] == [
        "RN1",
        "RN2",
        "RN3",
    ]
    assert [item["id"] for item in report["internal"]["support_handoff"]] == [
        "SH1",
        "SH2",
        "SH3",
    ]
    assert json.loads(render_design_brief_release_notes(report, fmt="json")) == report


def test_design_brief_release_notes_preserve_evidence_and_source_ideas(tmp_path) -> None:
    store, brief_id = _store_with_complete_brief(tmp_path)
    try:
        report = build_design_brief_release_notes(store, brief_id)
    finally:
        store.close()

    assert report is not None
    evidence = report["internal"]["validation_evidence"]
    signal = next(item for item in evidence if item["id"] == "sig-release-1")
    assert signal["kind"] == "signal"
    assert signal["summary"] == "Release proof"
    assert signal["source_type"] == "survey"
    assert signal["source_adapter"] == "test"
    assert signal["url"] == "https://example.com/release-proof"
    assert signal["credibility"] == 0.91
    assert signal["source_idea_ids"] == ["bu-release-lead"]
    assert any(item["id"] == "ins-release-1" for item in evidence)
    assert all(
        item["source_idea_ids"] == ["bu-release-lead", "bu-release-support"]
        for item in report["customer_facing"]["shipped_capabilities"]
    )


def test_render_design_brief_release_notes_markdown_is_stable(tmp_path) -> None:
    store, brief_id = _store_with_complete_brief(tmp_path)
    try:
        report = build_design_brief_release_notes(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_release_notes(report, fmt="markdown")

    assert markdown.startswith("# Release Notes: Release Notes Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Customer-Facing Notes" in markdown
    assert "### Shipped Capabilities" in markdown
    assert "### Target Users" in markdown
    assert "### Rollout Notes" in markdown
    assert "### Known Limitations" in markdown
    assert "### Follow-Up Milestones" in markdown
    assert "## Internal Notes" in markdown
    assert "### Validation Evidence" in markdown
    assert "### Support Handoff" in markdown
    assert "- **CAP1-ready release-notes generation**" not in markdown
    assert "- **Release proof**" not in markdown
    assert "- **sig-release-1** (signal): Release proof" in markdown


def test_design_brief_release_notes_sparse_brief_uses_readable_fallbacks(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_release_notes(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["release_stage"] == "internal_draft"
    assert report["summary"]["fallbacks_used"] == [
        "specific_user",
        "buyer",
        "workflow_context",
        "mvp_scope",
    ]
    assert report["summary"]["target_user"] == "Sparse Release Brief user"
    assert report["customer_facing"]["shipped_capabilities"][0]["title"] == (
        "First usable Sparse Release Brief workflow"
    )
    assert report["customer_facing"]["known_limitations"][0]["description"] == (
        "No explicit launch limitation was captured in the design brief."
    )

    markdown = render_design_brief_release_notes(report, fmt="markdown")
    assert "Source ideas: bu-release-sparse" in markdown
    assert "Fallbacks used: specific_user, buyer, workflow_context, mvp_scope" in markdown
    assert "### Validation Evidence" in markdown


def test_design_brief_release_notes_missing_brief_filename_and_invalid_format(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_release_notes.db"), wal_mode=True)
    try:
        assert build_design_brief_release_notes(store, "dbf-missing") is None
    finally:
        store.close()

    assert (
        release_notes_filename({"id": "dbf-123", "title": "Release Notes: Alpha / Beta"})
        == "dbf-123-Release-Notes-Alpha-Beta-release-notes.md"
    )
    assert (
        release_notes_filename(
            {"id": "dbf-123", "title": "Release Notes: Alpha / Beta"}, fmt="json"
        )
        == "dbf-123-Release-Notes-Alpha-Beta-release-notes.json"
    )
    with pytest.raises(ValueError, match="Unsupported release notes format: yaml"):
        render_design_brief_release_notes({"design_brief": {}}, fmt="yaml")


def _store_with_complete_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_release_notes.db"), wal_mode=True)
    store.insert_signal(
        Signal(
            id="sig-release-1",
            source_type=SignalSourceType.SURVEY,
            source_adapter="test",
            title="Release proof",
            content="Pilot operators confirmed the release notes workflow.",
            url="https://example.com/release-proof",
            tags=["validation", "launch"],
            credibility=0.91,
            metadata={"signal_role": "validation"},
        )
    )
    lead = BuildableUnit(
        id="bu-release-lead",
        title="Release Notes Lead",
        one_liner="Generate launch communication from a design brief.",
        category="application",
        problem="Teams lose launch context after idea synthesis.",
        solution="Generate release notes with customer and internal sections.",
        value_proposition="Close the loop from design brief to launch communication.",
        specific_user="platform operator",
        buyer="engineering director",
        workflow_context="developer platform launch handoff",
        current_workaround="manual changelog drafting",
        why_now="Design brief artifacts already cover execution handoff.",
        validation_plan="Confirm release notes with two launch owners.",
        first_10_customers="internal platform teams",
        domain_risks=["Claims may outrun validation evidence."],
        evidence_signals=["sig-release-1"],
        inspiring_insights=["ins-release-1"],
        domain="developer-tools",
        status="approved",
    )
    supporting = BuildableUnit(
        id="bu-release-support",
        title="Release Notes Support",
        one_liner="Carry support context into launch notes.",
        category="application",
        problem="Support teams do not know launch limitations.",
        solution="Include known limitations and support handoff.",
        value_proposition="Reduce release support ambiguity.",
        specific_user="support lead",
        buyer="support director",
        workflow_context="support launch readiness",
        domain_risks=["Support ownership may be unclear."],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Release Notes Brief",
            domain="developer-tools",
            theme="launch-communication",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=88.0,
            why_this_now="Launch communication should reuse persisted brief context.",
            merged_product_concept="Deterministic release notes for design brief launches.",
            synthesis_rationale="The artifact closes the loop from idea generation to launch.",
            mvp_scope=["release-notes generation", "customer/internal section split"],
            first_milestones=["Publish release notes artifact", "Review first launch feedback"],
            validation_plan="Confirm release notes with two launch owners.",
            risks=["Claims may outrun validation evidence."],
            source_idea_ids=[lead.id, supporting.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_sparse_release_notes.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-release-sparse",
        title="Sparse Release Lead",
        one_liner="Generate release notes with missing launch fields.",
        category="application",
        problem="Release context can be incomplete.",
        solution="Use deterministic fallback release-note language.",
        value_proposition="Keep launch communication drafts readable.",
        validation_plan="Review fallback notes internally.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Release Brief",
            domain="developer-tools",
            theme="launch-communication",
            lead=Candidate(unit=lead),
            readiness_score=41.0,
            why_this_now="The team needs a draft before all fields are complete.",
            merged_product_concept="Readable release notes for sparse briefs.",
            synthesis_rationale="Tests sparse release-note behavior.",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="Review fallback notes internally.",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="candidate",
        )
    )
    return store, brief_id
