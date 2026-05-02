from __future__ import annotations

import csv
from io import StringIO

import pytest

from max.analysis.market_sizing import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_market_sizing_report,
    market_sizing_filename,
    render_market_sizing_report,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _signal(signal_id: str, source_type: SignalSourceType, adapter: str, role: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=adapter,
        title=f"{role.title()} evidence",
        content=f"Evidence for {role}",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.8,
        metadata={"signal_role": role},
    )


def _unit(unit_id: str, signal_ids: list[str], insight_ids: list[str]) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Agent Workflow Guard",
        one_liner="Agent release checks for platform teams",
        category="application",
        problem="Platform teams cannot quantify agent release risk.",
        solution="A CI gate with workflow fixtures and evidence reports.",
        value_proposition="Reduce unsafe agent releases.",
        specific_user="platform engineer",
        buyer="engineering manager",
        workflow_context="agent release approval",
        current_workaround="manual prompt review",
        why_now="Agents are entering production workflows.",
        validation_plan="Interview platform teams.",
        first_10_customers="platform teams",
        evidence_rationale="Signals show budget and demand.",
        inspiring_insights=insight_ids,
        evidence_signals=signal_ids,
        domain="developer-tools",
        status="approved",
    )


def _evaluation(unit_id: str, score: float) -> UtilityEvaluation:
    dim = DimensionScore(value=8.0, confidence=0.7, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=score,
        recommendation="yes",
    )


def _seed_report_brief(tmp_path) -> tuple[Store, dict]:
    store = Store(str(tmp_path / "max.db"))
    for signal in [
        _signal("sig-survey", SignalSourceType.SURVEY, "stackoverflow_survey", "market"),
        _signal("sig-funding", SignalSourceType.FUNDING, "github_funding", "market"),
        _signal("sig-security", SignalSourceType.SECURITY, "nvd_cve", "security"),
        _signal("sig-forum", SignalSourceType.FORUM, "hackernews", "problem"),
    ]:
        store.insert_signal(signal)
    store.insert_insight(
        Insight(
            id="ins-market",
            category=InsightCategory.EMERGING_PATTERN,
            title="Production agent demand",
            summary="Teams are looking for release evidence.",
            evidence=["sig-survey", "sig-funding"],
            confidence=0.8,
            domains=["developer-tools"],
        )
    )
    lead = _unit("bu-market-lead", ["sig-forum", "sig-security"], ["ins-market"])
    store.insert_buildable_unit(lead)
    store.insert_evaluation(_evaluation("bu-market-lead", 81.0))
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Agent Workflow Guard",
            domain="developer-tools",
            theme="agent-release-safety",
            lead=Candidate(unit=lead),
            readiness_score=86.0,
            why_this_now="Agents are entering production workflows.",
            merged_product_concept="A CI release gate for agent workflow safety.",
            synthesis_rationale="Demand and risk signals point to platform teams.",
            mvp_scope=["CI fixture runner"],
            first_milestones=["Run pilot"],
            validation_plan="Interview platform teams.",
            risks=["Security urgency may not imply budget."],
            source_idea_ids=["bu-market-lead"],
        )
    )
    brief = store.get_design_brief(brief_id)
    assert brief is not None
    return store, brief


def test_build_market_sizing_report_uses_persisted_lineage_and_counts(tmp_path) -> None:
    store, brief = _seed_report_brief(tmp_path)
    try:
        report = build_market_sizing_report(store, brief)
        repeated = build_market_sizing_report(store, brief)
    finally:
        store.close()

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["design_brief"]["id"] == brief["id"]
    assert report["signal_counts"]["survey"] == 1
    assert report["signal_counts"]["funding"] == 1
    assert report["signal_counts"]["security"] == 1
    assert report["signal_counts"]["forum"] == 1
    assert report["evaluation_summary"]["evaluated_source_ideas"] == 1
    assert report["confidence"]["level"] in {"medium", "high"}

    segment = report["segments"][0]
    assert segment["buyer"] == "engineering manager"
    assert segment["user"] == "platform engineer"
    assert segment["source_idea_ids"] == ["bu-market-lead"]
    assert segment["signal_counts"]["total"] == 4
    assert segment["evidence_strength"] in {"moderate", "strong"}
    assert report["recommendations"]


def test_build_market_sizing_report_surfaces_missing_market_evidence(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    unit = BuildableUnit(
        id="bu-thin-market",
        title="Thin Market",
        one_liner="Thin market evidence",
        category="application",
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        domain="unknown-domain",
        status="approved",
    )
    store.insert_buildable_unit(unit)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Thin Market",
            domain="unknown-domain",
            theme="thin",
            lead=Candidate(unit=unit),
            readiness_score=40.0,
            why_this_now="",
            merged_product_concept="Solution",
            synthesis_rationale="",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            source_idea_ids=["bu-thin-market"],
        )
    )
    brief = store.get_design_brief(brief_id)
    assert brief is not None
    try:
        report = build_market_sizing_report(store, brief)
    finally:
        store.close()

    assert report["confidence"]["level"] == "low"
    assert "No quantified survey evidence is linked to the brief lineage." in report["gaps"]
    assert "No funding signal is linked to the brief lineage." in report["gaps"]
    assert report["segments"][0]["evidence_strength"] == "weak"


def test_render_market_sizing_report_csv_has_stable_rows_and_header(tmp_path) -> None:
    store, brief = _seed_report_brief(tmp_path)
    try:
        report = build_market_sizing_report(store, brief)
        report["gaps"] = ["Security urgency may not imply budget."]
        csv_text = render_market_sizing_report(report, fmt="csv")
        repeated = render_market_sizing_report(report, fmt="csv")
    finally:
        store.close()

    assert csv_text == repeated
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)

    reader = csv.DictReader(StringIO(csv_text))
    rows = list(reader)
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert rows

    estimate_rows = [row for row in rows if row["row_type"] == "estimate"]
    assert [row["estimate_scope"] for row in estimate_rows[:3]] == ["TAM", "SAM", "SOM"]
    assert estimate_rows[0]["segment_name"] == "engineering manager / platform engineer"
    assert estimate_rows[0]["buyer"] == "engineering manager"
    assert estimate_rows[0]["user"] == "platform engineer"
    assert estimate_rows[0]["source_idea_ids"] == "bu-market-lead"
    assert estimate_rows[0]["survey_signals"] == "1"
    assert estimate_rows[0]["funding_signals"] == "1"
    assert estimate_rows[0]["security_signals"] == "1"
    assert estimate_rows[0]["forum_signals"] == "1"
    assert estimate_rows[0]["total_signals"] == "4"
    assert "survey=1" in estimate_rows[0]["evidence"]
    assert "adapters=" in estimate_rows[0]["evidence"]
    assert estimate_rows[0]["assumption"]
    assert estimate_rows[0]["confidence_level"] in {"medium", "high"}
    assert estimate_rows[0]["confidence_score"]
    assert estimate_rows[0]["risk"]
    assert estimate_rows[0]["next_step"]
    assert any(row["row_type"] == "assumption" for row in rows)
    assert any(row["row_type"] == "risk" for row in rows)
    assert any(row["row_type"] == "next_step" for row in rows)


def test_render_market_sizing_report_csv_uses_csv_quoting(tmp_path) -> None:
    store, brief = _seed_report_brief(tmp_path)
    try:
        report = build_market_sizing_report(store, brief)
    finally:
        store.close()
    report["market_hypotheses"] = ['Budget owner says "yes", if audit trail is clear.']

    csv_text = render_market_sizing_report(report, fmt="csv")

    assert '"Budget owner says ""yes"", if audit trail is clear."' in csv_text
    rows = list(csv.DictReader(StringIO(csv_text)))
    assert rows[0]["assumption"] == 'Budget owner says "yes", if audit trail is clear.'


def test_render_market_sizing_report_csv_sparse_report_is_header_only() -> None:
    assert render_market_sizing_report({}, fmt="csv") == ",".join(CSV_COLUMNS) + "\n"
    assert (
        render_market_sizing_report({"design_brief": {"id": "brief-1"}, "segments": []}, fmt="csv")
        == ",".join(CSV_COLUMNS) + "\n"
    )


def test_render_market_sizing_report_rejects_invalid_format(tmp_path) -> None:
    store, brief = _seed_report_brief(tmp_path)
    try:
        report = build_market_sizing_report(store, brief)
    finally:
        store.close()

    with pytest.raises(ValueError, match="Unsupported market sizing format: yaml"):
        render_market_sizing_report(report, fmt="yaml")


def test_market_sizing_filename_uses_csv_extension(tmp_path) -> None:
    store, brief = _seed_report_brief(tmp_path)
    try:
        report = build_market_sizing_report(store, brief)
    finally:
        store.close()

    assert market_sizing_filename(report["design_brief"], fmt="csv").endswith(
        "-market-sizing.csv"
    )
