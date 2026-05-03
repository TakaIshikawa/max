from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_gtm_channel_plan import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_design_brief_gtm_channel_plan,
    gtm_channel_plan_filename,
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


def test_render_design_brief_gtm_channel_plan_csv_recommendations_are_stable(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_gtm_brief(store)
        report = build_design_brief_gtm_channel_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report["experiments"] = [
        {
            "id": "EXP-COPY",
            "name": "Problem-led email copy test",
            "channel": "design partner outreach",
            "owner": "product marketing",
            "priority": 1,
            "hypothesis": "Problem-first copy improves qualified reply rate.",
            "metric": "qualified_conversation_rate",
            "variants": ["workflow pain", "business case"],
            "source_idea_ids": ["bu-gtm-lead"],
        }
    ]
    report["next_actions"] = [
        {
            "id": "NA-CAMPAIGN",
            "action": "Create campaign tracker rows from the validation channels.",
            "channel": "design partner outreach",
            "owner": "growth lead",
            "priority": "P0",
            "source_idea_ids": ["bu-gtm-lead"],
            "due_in_days": 3,
        }
    ]
    csv_text = render_design_brief_gtm_channel_plan(report, "csv")
    repeated = render_design_brief_gtm_channel_plan(report, "csv")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    assert csv_text == repeated
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert [row["section"] for row in rows] == [
        *["channel_recommendations"] * 3,
        "experiments",
        *["launch_motions"] * 3,
        *["metrics"] * 3,
        "risks",
        "next_actions",
    ]
    first = rows[0]
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == KIND
    assert first["design_brief_id"] == brief_id
    assert first["design_brief_title"] == "Launch Workflow Copilot Brief"
    assert first["domain"] == "developer-tools"
    assert first["theme"] == "gtm-channel-plan"
    assert first["design_status"] == "approved"
    assert first["readiness_score"] == "87.0"
    assert first["section"] == "channel_recommendations"
    assert first["item_id"] == "GTM1"
    assert first["item_name"] == "design partner outreach"
    assert first["priority"] == "1"
    assert first["channel"] == "design partner outreach"
    assert first["owner"] == "product marketing"
    assert first["rationale"].startswith("Direct outreach is the fastest way")
    assert first["metric"] == "qualified_conversation_rate"
    assert json.loads(first["source_idea_ids"]) == ["bu-gtm-lead"]
    detail = json.loads(first["detail"])
    assert detail["audience"] == "developer tools founder"
    assert detail["call_to_action"] == "Schedule a 30-minute workflow review."
    assert detail["confidence"] == "high"
    assert detail["evidence_refs"] == [
        "sig-gtm-forum",
        "sig-gtm-funding",
        "sig-gtm-survey",
    ]
    experiment = next(row for row in rows if row["section"] == "experiments")
    assert experiment["item_id"] == "EXP-COPY"
    assert experiment["item_name"] == "Problem-led email copy test"
    assert experiment["metric"] == "qualified_conversation_rate"
    assert json.loads(experiment["detail"]) == {"variants": ["workflow pain", "business case"]}
    assert rows[-1]["section"] == "next_actions"
    assert rows[-1]["item_id"] == "NA-CAMPAIGN"
    assert rows[-1]["item_name"] == "Create campaign tracker rows from the validation channels."
    assert rows[-1]["channel"] == "design partner outreach"
    assert rows[-1]["owner"] == "growth lead"
    assert rows[-1]["priority"] == "P0"
    assert json.loads(rows[-1]["detail"]) == {"due_in_days": 3}


def test_render_design_brief_gtm_channel_plan_csv_serializes_nested_detail_cells(
    tmp_path,
) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_gtm_brief(store)
        report = build_design_brief_gtm_channel_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rows = list(csv.DictReader(io.StringIO(render_design_brief_gtm_channel_plan(report, "csv"))))
    first = rows[0]
    detail = json.loads(first["detail"])

    assert [tactic["name"] for tactic in detail["tactics"]] == [
        "warm account list",
        "problem-led email",
    ]
    assert [tactic["description"] for tactic in detail["tactics"]] == [
        "Identify existing relationships with developer tools founder ownership.",
        "Lead with the design partner recruiting pain and request validation.",
    ]
    assert [tactic["owner"] for tactic in detail["tactics"]] == [
        "product marketing",
        "founder or product lead",
    ]
    assert detail["success_metric"] == {
        "metric": "qualified_conversation_rate",
        "target": "25%+ positive replies from qualified accounts",
    }
    assert first["detail"] == json.dumps(detail, sort_keys=True, separators=(",", ":"))
    launch = next(row for row in rows if row["section"] == "launch_motions")
    assert launch["item_id"] == "LM1"
    assert launch["item_name"] == "validation"
    assert json.loads(launch["channel"]) == [
        "design partner outreach",
        "buyer enablement content",
    ]
    assert launch["metric"] == "At least three qualified conversations confirm urgency and wording."
    metric = next(row for row in rows if row["section"] == "metrics")
    assert metric["item_id"] == "M1"
    assert metric["metric"] == "qualified_conversation_rate"
    assert json.loads(metric["detail"]) == {
        "definition": (
            "Share of design partner outreach responses that match developer tools founder "
            "and design partner recruiting."
        ),
        "target": "25%+ positive replies from qualified accounts",
    }
    risk = next(row for row in rows if row["section"] == "risks")
    assert risk["item_id"] == "R1"
    assert risk["owner"] == "product marketing"
    assert json.loads(risk["detail"]) == {
        "mitigation": (
            "Validate through design partner outreach before scaling community proof loop."
        )
    }


def test_render_design_brief_gtm_channel_plan_csv_escapes_special_characters(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_gtm_brief(store)
        report = build_design_brief_gtm_channel_plan(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report = json.loads(json.dumps(report))
    recommendation = report["channel_recommendations"][0]
    recommendation["channel"] = 'design, partner "alpha"\noutreach'
    recommendation["rationale"] = 'Use "quoted", comma-led\ncopy.'
    recommendation["tactics"][0]["description"] = 'List "warm", accounts\ncarefully.'
    report["sequencing"][0]["channels"][0] = recommendation["channel"]
    report["launch_sequence"][0]["channels"][0] = recommendation["channel"]

    rows = list(csv.DictReader(io.StringIO(render_design_brief_gtm_channel_plan(report, "csv"))))
    detail = json.loads(rows[0]["detail"])

    assert rows[0]["channel"] == 'design, partner "alpha"\noutreach'
    assert rows[0]["rationale"] == 'Use "quoted", comma-led\ncopy.'
    assert detail["tactics"][0]["description"] == 'List "warm", accounts\ncarefully.'
    launch = next(row for row in rows if row["section"] == "launch_motions")
    assert json.loads(launch["channel"])[0] == 'design, partner "alpha"\noutreach'


def test_render_design_brief_gtm_channel_plan_csv_header_only_without_recommendations() -> None:
    csv_text = render_design_brief_gtm_channel_plan(
        {"design_brief": {"id": "dbf-empty"}, "channel_recommendations": []},
        "csv",
    )

    assert csv_text == ",".join(CSV_COLUMNS) + "\n"
    assert list(csv.DictReader(io.StringIO(csv_text))) == []


def test_gtm_channel_plan_filename_supports_csv() -> None:
    assert (
        gtm_channel_plan_filename({"id": "dbf-gtm/csv"}, fmt="markdown")
        == "dbf-gtm-csv-gtm-channel-plan.md"
    )
    assert (
        gtm_channel_plan_filename({"id": "dbf-gtm/csv"}, fmt="json")
        == "dbf-gtm-csv-gtm-channel-plan.json"
    )
    assert (
        gtm_channel_plan_filename({"id": "dbf-gtm/csv"}, fmt="csv")
        == "dbf-gtm-csv-gtm-channel-plan.csv"
    )


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
