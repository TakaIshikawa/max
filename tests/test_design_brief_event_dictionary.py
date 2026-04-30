"""Tests for design brief analytics event dictionary generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_event_dictionary import (
    CATEGORIES,
    KIND,
    PROPERTY_LIMIT,
    SCHEMA_VERSION,
    build_design_brief_event_dictionary,
    event_dictionary_filename,
    render_design_brief_event_dictionary,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_build_design_brief_event_dictionary_structured_output(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        first = build_design_brief_event_dictionary(store, brief_id)
        second = build_design_brief_event_dictionary(store, brief_id)
    finally:
        store.close()

    assert first is not None
    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == KIND
    assert first["design_brief"]["id"] == brief_id
    assert first["design_brief"]["source_idea_ids"] == [
        "bu-event-dictionary-lead",
        "bu-event-dictionary-support",
    ]
    assert first["summary"]["event_group_count"] == 5
    assert first["summary"]["event_count"] == 10
    assert first["summary"]["max_properties_per_event"] <= PROPERTY_LIMIT
    assert [group["category"] for group in first["event_groups"]] == list(CATEGORIES)
    assert {event["category"] for event in first["events"]} == set(CATEGORIES)
    assert json.loads(json.dumps(first))["schema_version"] == SCHEMA_VERSION


def test_events_include_required_contract_fields_and_source_context(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_event_dictionary(store, brief_id)
    finally:
        store.close()

    assert report is not None
    event_names = [event["event_name"] for event in report["events"]]
    assert event_names == [
        "design_brief_workflow_started",
        "design_brief_first_value_reached",
        "design_brief_scope_item_completed",
        "design_brief_evidence_referenced",
        "design_brief_workflow_repeated",
        "design_brief_retention_checkpoint_met",
        "design_brief_pilot_accepted",
        "design_brief_success_metric_confirmed",
        "design_brief_risk_guardrail_triggered",
        "design_brief_privacy_payload_rejected",
    ]
    assert all(_is_snake_case(event["event_name"]) for event in report["events"])
    assert all(
        {
            "event_name",
            "category",
            "trigger",
            "actor",
            "properties",
            "privacy_notes",
            "linked_metric",
            "source_idea_ids",
            "implementation_priority",
        }
        <= set(event)
        for event in report["events"]
    )
    assert all(0 < len(event["properties"]) <= PROPERTY_LIMIT for event in report["events"])
    assert any("release governance review" in event["trigger"] for event in report["events"])
    assert any("JSON event dictionary export" in event["trigger"] for event in report["events"])
    assert all(event["linked_metric"] for event in report["events"])
    assert all(event["source_idea_ids"] == report["design_brief"]["source_idea_ids"] for event in report["events"])


def test_property_contracts_include_privacy_notes_for_sensitive_property_families(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_event_dictionary(store, brief_id)
    finally:
        store.close()

    assert report is not None
    contracts = {contract["name"]: contract for contract in report["property_contracts"]}
    assert "user_id" in contracts
    assert "account_id" in contracts
    assert "workflow_context" in contracts
    assert "evidence_id" in contracts
    assert "names, emails" in contracts["user_id"]["privacy_note"]
    assert "customer names" in contracts["account_id"]["privacy_note"]
    assert "raw task descriptions" in contracts["workflow_context"]["privacy_note"]
    assert "evidence ids only" in contracts["evidence_id"]["privacy_note"].lower()
    assert contracts["severity"]["allowed_values"] == ["low", "medium", "high", "critical"]
    assert contracts["guardrail_type"]["allowed_values"] == [
        "adoption",
        "privacy",
        "security",
        "workflow",
        "data_quality",
    ]
    assert any(
        "evidence ids only" in note.lower()
        for event in report["events"]
        if "evidence_id" in event["properties"]
        for note in event["privacy_notes"]
    )


def test_render_design_brief_event_dictionary_markdown_and_json(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_event_dictionary(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered_json = render_design_brief_event_dictionary(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_event_dictionary(report, fmt="markdown")
    assert markdown.startswith("# Analytics Event Dictionary: Event Dictionary Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Linked Metrics" in markdown
    assert "`activation_rate`" in markdown
    assert "`conversion_rate`" in markdown
    assert "## Activation Events" in markdown
    assert "## Engagement Events" in markdown
    assert "## Retention Events" in markdown
    assert "## Conversion Events" in markdown
    assert "## Guardrail Events" in markdown
    assert "| Event | Trigger | Actor | Linked Metric | Priority | Properties |" in markdown
    assert "`design_brief_workflow_started`" in markdown
    assert "`design_brief_risk_guardrail_triggered`" in markdown
    assert "## Property Contracts" in markdown
    assert "### `workflow_context`" in markdown


def test_sparse_design_brief_event_dictionary_uses_fallback_context(tmp_path) -> None:
    store, brief_id = _store_with_sparse_brief(tmp_path)
    try:
        report = build_design_brief_event_dictionary(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["fallbacks_used"] == ["specific_user", "buyer", "workflow_context"]
    assert report["event_context"]["target_user"] == "Sparse Event Brief user"
    assert report["event_context"]["buyer"] == "account sponsor"
    assert report["event_context"]["primary_scope"] == "Fallback contract"
    assert any(
        "Sparse Event Brief workflow" in event["trigger"]
        for event in report["events"]
    )


def test_event_dictionary_filename_missing_brief_and_invalid_format(tmp_path) -> None:
    assert (
        event_dictionary_filename({"id": "dbf-123", "title": "Event Dictionary: Alpha / Beta"})
        == "dbf-123-Event-Dictionary-Alpha-Beta-event-dictionary.md"
    )
    assert (
        event_dictionary_filename(
            {"id": "dbf-123", "title": "Event Dictionary: Alpha / Beta"}, fmt="json"
        )
        == "dbf-123-Event-Dictionary-Alpha-Beta-event-dictionary.json"
    )

    store = Store(db_path=str(tmp_path / "missing_event_dictionary.db"), wal_mode=True)
    try:
        assert build_design_brief_event_dictionary(store, "dbf-missing") is None
    finally:
        store.close()

    with pytest.raises(ValueError, match="Unsupported event dictionary format: yaml"):
        render_design_brief_event_dictionary({"design_brief": {}}, fmt="yaml")


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_event_dictionary.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-event-dictionary-lead",
        title="Event Dictionary Lead",
        one_liner="Create concrete analytics event contracts for design briefs.",
        category="application",
        problem="Implementation agents lack stable telemetry contracts.",
        solution="Generate event definitions and bounded properties from persisted briefs.",
        value_proposition="Make success metric instrumentation consistent across builds.",
        specific_user="platform engineer",
        buyer="VP of Engineering",
        workflow_context="release governance review",
        current_workaround="manual analytics spreadsheet",
        why_now="Design briefs already capture scope, risks, and validation inputs.",
        validation_plan="Review event contracts with platform engineers before implementation.",
        first_10_customers="platform teams shipping production agents",
        domain_risks=["Security approval may block rollout."],
        evidence_signals=["sig-event-1"],
        inspiring_insights=["ins-event-1"],
        domain="developer-tools",
        status="approved",
    )
    supporting = BuildableUnit(
        id="bu-event-dictionary-support",
        title="Event Dictionary Support",
        one_liner="Link telemetry events to validation evidence.",
        category="application",
        problem="Analytics plans do not define property contracts.",
        solution="Attach event names, properties, and privacy notes to a brief.",
        value_proposition="Help implementation agents instrument safely.",
        specific_user="analytics engineer",
        buyer="data leader",
        workflow_context="analytics implementation handoff",
        domain_risks=["Customer evidence may include sensitive content."],
        evidence_signals=["sig-event-2"],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Event Dictionary Brief",
            domain="developer-tools",
            theme="event-dictionary",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=87.0,
            why_this_now="Agents need telemetry contracts before implementing generated specs.",
            merged_product_concept="A release governance analytics dictionary for persisted design briefs.",
            synthesis_rationale="Turns brief scope and validation needs into event definitions.",
            mvp_scope=["JSON event dictionary export", "Markdown event dictionary export"],
            first_milestones=["Implementation agent instruments the first event group"],
            validation_plan="Review event contracts with platform engineers before implementation.",
            risks=["Security approval may block rollout.", "Evidence notes may contain sensitive content."],
            source_idea_ids=[lead.id, supporting.id],
            design_status="approved",
        )
    )
    return store, brief_id


def _store_with_sparse_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_sparse_event_dictionary.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-event-dictionary-sparse",
        title="Sparse Event Lead",
        one_liner="Create event contracts with weak context.",
        category="application",
        problem="Telemetry input is incomplete.",
        solution="Use deterministic fallback event contracts.",
        value_proposition="Keep instrumentation handoff moving.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Sparse Event Brief",
            domain="developer-tools",
            theme="event-dictionary",
            lead=Candidate(unit=lead),
            readiness_score=43.0,
            why_this_now="The team needs a draft before event naming review.",
            merged_product_concept="A sparse event dictionary.",
            synthesis_rationale="Tests fallback event contract generation.",
            mvp_scope=["Fallback contract"],
            first_milestones=["Review first event"],
            validation_plan="Review fallback contracts internally.",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="candidate",
        )
    )
    return store, brief_id


def _is_snake_case(value: str) -> bool:
    return value == value.lower() and "-" not in value and " " not in value
