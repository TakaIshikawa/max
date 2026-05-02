from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.design_brief_pricing_strategy import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_pricing_strategy,
    pricing_strategy_filename,
    render_design_brief_pricing_strategy,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _signal(signal_id: str, source_type: SignalSourceType, role: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=f"{role}-fixture",
        title=f"{role.title()} pricing evidence",
        content=f"Evidence for {role} pricing validation.",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.8,
        metadata={"signal_role": role},
    )


def _unit(unit_id: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Agent Pricing Guard",
        one_liner="Pricing strategy source idea",
        category="application",
        problem="Platform teams cannot price recurring agent release reviews.",
        solution="Run release workflow checks and report value to buyers.",
        value_proposition="Reduce risky releases and wasted review time.",
        specific_user="platform engineer",
        buyer="VP of Engineering",
        workflow_context="agent release workflow review",
        current_workaround="manual reviews and spreadsheets",
        why_now="Agent releases are moving into production.",
        validation_plan="Run paid pilot interviews with platform teams.",
        first_10_customers="platform teams shipping production agents",
        evidence_signals=["sig-pricing-survey", "sig-pricing-funding"],
        inspiring_insights=["ins-pricing-demand"],
        domain="developer-tools",
        status="approved",
    )


def _evaluation(unit_id: str) -> UtilityEvaluation:
    dim = DimensionScore(value=8.0, confidence=0.75, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=DimensionScore(value=5.0, confidence=0.7, reasoning="some alternatives"),
        timing_fit=dim,
        compounding_value=dim,
        overall_score=82.0,
        strengths=["clear buyer"],
        weaknesses=["needs pricing proof"],
        recommendation="yes",
        weights_used={"addressable_scale": 0.2},
    )


def _seed_pricing_brief(store: Store) -> str:
    survey = _signal("sig-pricing-survey", SignalSourceType.SURVEY, "market")
    funding = _signal("sig-pricing-funding", SignalSourceType.FUNDING, "budget")
    forum = _signal("sig-pricing-forum", SignalSourceType.FORUM, "problem")
    for signal in (survey, funding, forum):
        store.insert_signal(signal)
    store.insert_insight(
        Insight(
            id="ins-pricing-demand",
            category=InsightCategory.EMERGING_PATTERN,
            title="Pricing strategy demand",
            summary="Teams need clear paid pilot packaging.",
            evidence=[forum.id],
            confidence=0.8,
            domains=["developer-tools"],
        )
    )

    lead = _unit("bu-pricing-lead")
    store.insert_buildable_unit(lead)
    store.insert_evaluation(_evaluation(lead.id))
    store.insert_prior_art_match(
        lead.id,
        {
            "source": "github",
            "title": "agent-release-pricing-alternative",
            "url": "https://github.com/example/agent-release-pricing-alternative",
            "description": "Alternative release workflow review tool.",
            "relevance_score": 0.86,
            "match_signals": {"stars": 75},
            "search_query": "agent release review pricing",
        },
    )
    return store.insert_design_brief(
        ProjectBrief(
            title="Agent Pricing Guard Brief",
            domain="developer-tools",
            theme="pricing-strategy",
            lead=Candidate(unit=lead),
            readiness_score=84.0,
            why_this_now="Agent releases are moving into production.",
            merged_product_concept="A recurring release workflow review for platform teams.",
            synthesis_rationale="Signals show demand, budget, and workflow pain.",
            mvp_scope=["Release workflow report", "Buyer value dashboard"],
            first_milestones=["Run three paid pilots"],
            validation_plan="Interview platform leads about price bands.",
            risks=["Budget may sit outside platform teams."],
            source_idea_ids=[lead.id],
        )
    )


def test_build_design_brief_pricing_strategy_is_deterministic(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_pricing_brief(store)
        report = build_design_brief_pricing_strategy(store, brief_id)
        repeated = build_design_brief_pricing_strategy(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["design_brief"]["id"] == brief_id
    assert report["packages"][0]["name"] == "Starter"
    assert [band["package"] for band in report["price_bands"]] == ["Starter", "Team", "Business"]
    assert report["value_metric"]["metric"] == "completed workflow runs"
    assert report["market_signals"]["survey"] == 1
    assert report["market_signals"]["funding"] == 1
    assert report["market_signals"]["forum"] == 1
    assert report["competitive_landscape_hints"]["prior_art_count"] == 1
    assert report["confidence"]["level"] in {"medium", "high"}
    assert [reference["id"] for reference in report["evidence_references"]] == [
        "sig-pricing-forum",
        "sig-pricing-funding",
        "sig-pricing-survey",
    ]


def test_render_design_brief_pricing_strategy_json_markdown_and_invalid_format(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_pricing_brief(store)
        report = build_design_brief_pricing_strategy(store, brief_id)
    finally:
        store.close()

    assert report is not None
    parsed = json.loads(render_design_brief_pricing_strategy(report, "json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_pricing_strategy(report, "markdown")
    assert markdown.startswith("# Pricing Strategy: Agent Pricing Guard Brief")
    assert "Schema: `max.design_brief.pricing_strategy.v1`" in markdown
    assert "## Recommended Packaging" in markdown
    assert "## Initial Price Bands" in markdown
    assert "## Buyer Objections" in markdown
    assert "sig-pricing-funding" in markdown

    with pytest.raises(ValueError):
        render_design_brief_pricing_strategy(report, "yaml")


def test_render_design_brief_pricing_strategy_csv_rows_and_filename(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_pricing_brief(store)
        report = build_design_brief_pricing_strategy(store, brief_id)
    finally:
        store.close()

    assert report is not None
    csv_text = render_design_brief_pricing_strategy(report, "csv")
    repeated = render_design_brief_pricing_strategy(report, "csv")
    reader = csv.DictReader(StringIO(csv_text))
    rows = list(reader)

    assert csv_text == repeated
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert [row["section"] for row in rows[:3]] == ["tier", "tier", "tier"]
    assert [row["package"] for row in rows[:3]] == ["Starter", "Team", "Business"]
    assert rows[0]["monthly_min_usd"] == "99"
    assert rows[0]["monthly_max_usd"] == "199"
    assert "Up to 100 runs/month" in rows[0]["detail"]
    assert "Release workflow report" in rows[0]["rationale"]
    assert any(row["section"] == "assumption" and row["item_id"] == "assumption-value-metric" for row in rows)
    assert any(row["section"] == "risk" and row["name"] == "Budget may sit outside platform teams." for row in rows)
    assert any(row["section"] == "experiment" and row["source"] == "validation_questions" for row in rows)
    assert pricing_strategy_filename(report["design_brief"], fmt="csv").endswith(".csv")


def test_render_design_brief_pricing_strategy_csv_missing_optional_sections(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_pricing_brief(store)
        report = build_design_brief_pricing_strategy(store, brief_id)
    finally:
        store.close()

    assert report is not None
    report.pop("key_assumptions")
    report.pop("risks")
    report.pop("recommended_experiments")

    csv_text = render_design_brief_pricing_strategy(report, "csv")
    reader = csv.DictReader(StringIO(csv_text))
    rows = list(reader)

    assert reader.fieldnames == list(CSV_COLUMNS)
    assert [row["section"] for row in rows] == ["tier", "tier", "tier"]


def test_build_design_brief_pricing_strategy_missing_brief_returns_none(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        assert build_design_brief_pricing_strategy(store, "dbf-missing") is None
    finally:
        store.close()
