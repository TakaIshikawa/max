from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from max.analysis.design_brief_evidence_quality_scorecard import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_evidence_quality_scorecard,
    render_design_brief_evidence_quality_scorecard,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _signal(
    signal_id: str,
    adapter: str,
    role: str,
    *,
    source_type: SignalSourceType = SignalSourceType.FORUM,
    published_at: datetime | None = None,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=adapter,
        title=f"{role.title()} signal",
        content=f"Recent credible {role} evidence for build execution.",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.85,
        published_at=published_at,
        fetched_at=published_at or datetime(2026, 4, 20, tzinfo=timezone.utc),
        metadata={"signal_role": role},
    )


def _unit(
    unit_id: str,
    *,
    insight_ids: list[str],
    signal_ids: list[str],
    title: str = "Agent Workflow Guard",
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner="Evidence-backed agent workflow release checks",
        category="application",
        problem="Platform teams cannot prove agent workflow safety before release.",
        solution="Run workflow fixtures with risk checks and release gates.",
        value_proposition="Reduce unsafe agent releases without slowing useful workflows.",
        specific_user="platform engineer deploying AI agents",
        buyer="engineering manager",
        workflow_context="CI gate before agent production deployment",
        current_workaround="manual prompt testing and spreadsheet review",
        why_now="Agent tool use is moving into production workflows.",
        validation_plan="Interview platform teams and run a smoke-test pilot.",
        first_10_customers="agent framework maintainers; platform teams",
        domain_risks=["Framework adapters may change quickly"],
        evidence_rationale="Signals show repeated workflow safety gaps.",
        inspiring_insights=insight_ids,
        evidence_signals=signal_ids,
        tech_approach="Python service with YAML fixtures",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
        quality_score=8.0,
    )


def _seed_high_quality_brief(tmp_path) -> tuple[Store, dict]:
    store = Store(str(tmp_path / "max.db"))
    published_at = datetime(2026, 4, 15, tzinfo=timezone.utc)
    signals = [
        _signal("sig-problem", "hackernews", "problem", published_at=published_at),
        _signal(
            "sig-market",
            "stackoverflow_survey",
            "market",
            source_type=SignalSourceType.SURVEY,
            published_at=published_at,
        ),
        _signal("sig-workflow", "github_issues", "workflow", published_at=published_at),
        _signal("sig-solution", "github_discussions", "solution", published_at=published_at),
        _signal(
            "sig-risk",
            "nvd_cve",
            "risk",
            source_type=SignalSourceType.SECURITY,
            published_at=published_at,
        ),
        _signal(
            "sig-validation",
            "product_hunt",
            "validation",
            source_type=SignalSourceType.EXPERIMENT,
            published_at=published_at,
        ),
    ]
    for signal in signals:
        store.insert_signal(signal)

    store.insert_insight(
        Insight(
            id="ins-gap",
            category=InsightCategory.GAP,
            title="Agent release safety gap",
            summary="Teams need repeatable release evidence for agent workflows.",
            evidence=["sig-problem", "sig-market", "sig-workflow"],
            confidence=0.9,
            domains=["developer-tools"],
        )
    )
    store.insert_insight(
        Insight(
            id="ins-risk",
            category=InsightCategory.VULNERABILITY,
            title="Workflow security risk",
            summary="Tool-using agents create workflow security exposure.",
            evidence=["sig-risk", "sig-validation"],
            confidence=0.85,
            domains=["developer-tools"],
        )
    )

    lead = _unit(
        "bu-lead",
        insight_ids=["ins-gap"],
        signal_ids=["sig-problem", "sig-workflow", "sig-solution"],
        title="Agent Workflow Guard",
    )
    supporting = _unit(
        "bu-support",
        insight_ids=["ins-risk"],
        signal_ids=["sig-market", "sig-risk", "sig-validation"],
        title="Agent Release Risk Monitor",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(supporting)

    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Agent Workflow Guard",
            domain="developer-tools",
            theme="agent-release-safety",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=supporting)],
            readiness_score=90.0,
            why_this_now="Agent tool use is entering production workflows.",
            merged_product_concept="A CI gate for agent workflow safety checks.",
            synthesis_rationale="Combines release safety pain with workflow risk monitoring.",
            mvp_scope=["Fixture runner", "Risk report"],
            first_milestones=["Run fixtures in CI", "Publish risk scorecards"],
            validation_plan="Interview platform teams and run a smoke-test pilot.",
            risks=["Framework churn could break adapters."],
            source_idea_ids=["bu-lead", "bu-support"],
            design_status="approved",
        )
    )
    brief = store.get_design_brief(brief_id)
    assert brief is not None
    return store, brief


def test_build_design_brief_evidence_quality_scorecard_scores_high_quality_brief(tmp_path) -> None:
    store, brief = _seed_high_quality_brief(tmp_path)
    try:
        scorecard = build_design_brief_evidence_quality_scorecard(
            store,
            brief,
            generated_at="2026-05-01T00:00:00+00:00",
        )
    finally:
        store.close()

    assert scorecard["schema_version"] == SCHEMA_VERSION
    assert scorecard["kind"] == KIND
    assert scorecard["source"]["id"] == brief["id"]
    assert scorecard["summary"]["band"] in {"ready", "monitor"}
    assert scorecard["summary"]["confidence"] in {"high", "medium"}
    assert not scorecard["blockers"]
    assert {dimension["id"] for dimension in scorecard["dimension_scores"]} == {
        "evidence_volume",
        "source_diversity",
        "recency",
        "role_balance",
        "contradiction_risk",
        "traceability",
    }
    assert all(dimension["score"] >= 70 for dimension in scorecard["dimension_scores"])
    assert scorecard["evidence_refs"]["signal_ids"] == [
        "sig-market",
        "sig-problem",
        "sig-risk",
        "sig-solution",
        "sig-validation",
        "sig-workflow",
    ]
    assert scorecard["evidence_refs"]["source_idea_ids"] == ["bu-lead", "bu-support"]


def test_build_design_brief_evidence_quality_scorecard_blocks_sparse_evidence(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    unit = BuildableUnit(
        id="bu-thin",
        title="Thin Brief",
        one_liner="Thin evidence",
        category="application",
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        domain="testing",
        status="approved",
    )
    store.insert_buildable_unit(unit)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Thin Brief",
            domain="testing",
            theme="thin",
            lead=Candidate(unit=unit),
            readiness_score=45.0,
            why_this_now="",
            merged_product_concept="Solution",
            synthesis_rationale="",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            source_idea_ids=["bu-thin"],
        )
    )
    brief = store.get_design_brief(brief_id)
    assert brief is not None
    try:
        scorecard = build_design_brief_evidence_quality_scorecard(
            store,
            brief,
            generated_at="2026-05-01T00:00:00+00:00",
        )
    finally:
        store.close()

    assert scorecard["summary"]["band"] == "blocked"
    assert scorecard["summary"]["confidence"] == "low"
    assert "Insufficient persisted evidence volume for build execution." in scorecard["blockers"]
    assert any("Traceability" == dimension["label"] for dimension in scorecard["dimension_scores"])
    assert scorecard["evidence_refs"]["signal_ids"] == []
    assert any("Add at least three credible signals" in action for action in scorecard["recommended_next_evidence_actions"])


def test_render_design_brief_evidence_quality_scorecard_json_markdown_and_invalid_format(tmp_path) -> None:
    store, brief = _seed_high_quality_brief(tmp_path)
    try:
        scorecard = build_design_brief_evidence_quality_scorecard(
            store,
            brief,
            generated_at="2026-05-01T00:00:00+00:00",
        )
    finally:
        store.close()

    parsed = json.loads(render_design_brief_evidence_quality_scorecard(scorecard, fmt="json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_evidence_quality_scorecard(scorecard, fmt="markdown")
    assert markdown.startswith("# Evidence Quality Scorecard: Agent Workflow Guard")
    assert "## Dimension Scores" in markdown
    assert "### Evidence Volume" in markdown
    assert "### Source Diversity" in markdown
    assert "### Recency" in markdown
    assert "## Recommended Next Evidence Actions" in markdown
    assert "sig-problem" in markdown
    assert "bu-lead" in markdown

    with pytest.raises(ValueError):
        render_design_brief_evidence_quality_scorecard(scorecard, fmt="html")
