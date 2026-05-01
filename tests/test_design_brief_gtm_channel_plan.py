from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_gtm_channel_plan import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_gtm_channel_plan,
    render_design_brief_gtm_channel_plan,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def _signal(signal_id: str, source_type: SignalSourceType, role: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=f"{role}-fixture",
        title=f"{role.title()} GTM evidence",
        content=f"Evidence for {role} channel planning.",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.82,
        metadata={"signal_role": role},
    )


def _unit(unit_id: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Launch Workflow Copilot",
        one_liner="GTM channel plan source idea",
        category="application",
        problem="Developer tools founders cannot coordinate launch workflow decisions.",
        solution="Create a launch workflow cockpit with recommendations and status.",
        value_proposition="Reduce launch planning drift for developer tools teams.",
        specific_user="developer tools founder",
        buyer="growth lead",
        workflow_context="design partner recruiting",
        why_now="Launch-planning artifacts are ready for dashboards.",
        validation_plan="Review channel priorities with two launch owners.",
        first_10_customers="seed-stage developer tools companies",
        evidence_signals=["sig-gtm-forum", "sig-gtm-survey", "sig-gtm-funding"],
        domain_risks=["Message-market fit may vary by channel."],
        domain="developer-tools",
        status="approved",
    )


def _seed_gtm_brief(store: Store) -> str:
    for signal in (
        _signal("sig-gtm-forum", SignalSourceType.FORUM, "problem"),
        _signal("sig-gtm-survey", SignalSourceType.SURVEY, "market"),
        _signal("sig-gtm-funding", SignalSourceType.FUNDING, "budget"),
    ):
        store.insert_signal(signal)

    lead = _unit("bu-gtm-lead")
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Launch Workflow Copilot Brief",
            domain="developer-tools",
            theme="gtm-channel-plan",
            lead=Candidate(unit=lead),
            readiness_score=87.0,
            why_this_now="Launch-planning artifacts are ready for dashboards.",
            merged_product_concept="A deterministic launch channel plan for design briefs.",
            synthesis_rationale="Source ideas show direct launch workflow pain.",
            mvp_scope=["JSON GTM channel plan", "Markdown GTM channel plan"],
            first_milestones=["Return structured channel recommendations"],
            validation_plan="Confirm the REST payload preserves nested recommendation fields.",
            risks=["Message-market fit may vary by channel."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )


def _seed_sparse_brief(store: Store) -> str:
    lead = BuildableUnit(
        id="bu-gtm-sparse",
        title="Sparse GTM Idea",
        one_liner="Sparse source idea",
        category="application",
        problem="Missing GTM fields.",
        solution="Fill them later.",
        value_proposition="Make missing inputs visible.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Sparse GTM Brief",
            domain="developer-tools",
            theme="gtm-channel-plan",
            lead=Candidate(unit=lead),
            readiness_score=35.0,
            merged_product_concept="A sparse channel plan.",
            source_idea_ids=[lead.id],
        )
    )


def test_build_design_brief_gtm_channel_plan_is_deterministic_and_ranked(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_gtm_brief(store)
        report = build_design_brief_gtm_channel_plan(store, brief_id)
        repeated = build_design_brief_gtm_channel_plan(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["source"]["id"] == brief_id
    assert report["design_brief"]["id"] == brief_id
    assert report["design_brief"]["source_idea_ids"] == ["bu-gtm-lead"]
    assert report["summary"]["primary_channel"] == "design partner outreach"
    assert [item["id"] for item in report["channel_recommendations"]] == [
        "GTM1",
        "GTM2",
        "GTM3",
    ]
    assert [item["priority"] for item in report["channel_recommendations"]] == [1, 2, 3]
    first = report["channel_recommendations"][0]
    assert first["type"] == "acquisition"
    assert first["owner"] == "product marketing"
    assert first["confidence"] == "high"
    assert first["evidence_refs"] == ["sig-gtm-forum", "sig-gtm-funding", "sig-gtm-survey"]
    assert first["rationale"].startswith("Direct outreach is the fastest way")
    assert report["channels"]["partner"][0]["channel"] == "integration partner co-sell"
    assert report["channels"]["community"][0]["channel"] == "community proof loop"
    assert report["channels"]["sales_assisted"][0]["channel"] == "buyer enablement content"
    assert report["sequencing"][0]["channels"] == [
        "design partner outreach",
        "buyer enablement content",
    ]
    assert report["risks"][0]["risk"] == "Message-market fit may vary by channel."
    assert report["missing_inputs"] == []


def test_render_design_brief_gtm_channel_plan_json_markdown_and_invalid_format(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_gtm_brief(store)
        report = build_design_brief_gtm_channel_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    parsed = json.loads(render_design_brief_gtm_channel_plan(report, "json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_gtm_channel_plan(report, "markdown")
    assert markdown.startswith("# GTM Channel Plan: Launch Workflow Copilot Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Channel Recommendations" in markdown
    assert "design partner outreach" in markdown
    assert "## Sequencing Guidance" in markdown
    assert "## Measurement Plan" in markdown
    assert "sig-gtm-funding" in markdown

    with pytest.raises(ValueError):
        render_design_brief_gtm_channel_plan(report, "yaml")


def test_build_design_brief_gtm_channel_plan_reports_missing_inputs(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_sparse_brief(store)
        report = build_design_brief_gtm_channel_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    missing_fields = {item["field"] for item in report["missing_inputs"]}
    assert {"buyer", "specific_user", "workflow_context", "validation_plan", "risks"} <= missing_fields
    assert report["summary"]["confidence"] == "low"
    assert report["channel_recommendations"][0]["audience"] == "target user"


def test_build_design_brief_gtm_channel_plan_missing_brief_returns_none(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        assert build_design_brief_gtm_channel_plan(store, "dbf-missing") is None
    finally:
        store.close()
