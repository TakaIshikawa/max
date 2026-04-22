"""Tests for deterministic opportunity heatmap analysis."""

from __future__ import annotations

from datetime import datetime, timezone

from max.analysis.opportunity_heatmap import build_opportunity_heatmap
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _signal(signal_id: str, *, fetched_at: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title=f"Signal {signal_id}",
        content="Evidence",
        url=f"https://example.com/{signal_id}",
        fetched_at=datetime.fromisoformat(fetched_at).replace(tzinfo=timezone.utc),
        credibility=0.8,
    )


def _unit(
    unit_id: str,
    *,
    domain: str,
    category: str,
    evidence_signals: list[str],
    inspiring_insights: list[str] | None = None,
    status: str = "evaluated",
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="Test idea",
        category=category,
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        domain=domain,
        evidence_signals=evidence_signals,
        inspiring_insights=inspiring_insights or [],
        status=status,
    )


def _evaluation(unit_id: str, score: float) -> UtilityEvaluation:
    dim = DimensionScore(value=7.0, confidence=0.7, reasoning="test")
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


def test_build_opportunity_heatmap_groups_by_domain_and_category(store: Store) -> None:
    store.insert_signal(_signal("sig-1", fetched_at="2026-04-20T00:00:00"))
    store.insert_signal(_signal("sig-2", fetched_at="2026-04-21T00:00:00"))
    store.insert_insight(
        Insight(
            id="ins-1",
            category=InsightCategory.GAP,
            title="Gap",
            summary="Summary",
            evidence=["sig-2"],
            domains=["devtools"],
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-1",
            domain="devtools",
            category="cli_tool",
            evidence_signals=["sig-1"],
            inspiring_insights=["ins-1"],
        )
    )
    store.insert_evaluation(_evaluation("bu-1", 82.0))
    store.insert_feedback("bu-1", "approved", "strong")

    buckets = build_opportunity_heatmap(store)

    assert buckets == [
        {
            "domain": "devtools",
            "idea_category": "cli_tool",
            "signal_count": 2,
            "insight_count": 1,
            "idea_count": 1,
            "evaluated_count": 1,
            "approved_count": 1,
            "average_score": 82.0,
            "evidence_density": 67.5,
            "newest_fetched_at": "2026-04-21T00:00:00+00:00",
            "freshness_signal": 100.0,
            "opportunity_score": 85.6,
            "reasons": [
                "average evaluated score 82.0",
                "2 signal(s) and 1 insight(s) support 1 idea(s)",
                "newest evidence fetched at 2026-04-21T00:00:00+00:00",
                "1 approved or published idea(s)",
            ],
        }
    ]


def test_build_opportunity_heatmap_filters_domain_and_min_signals(store: Store) -> None:
    store.insert_signal(_signal("sig-dev", fetched_at="2026-04-21T00:00:00"))
    store.insert_signal(_signal("sig-fin", fetched_at="2026-04-22T00:00:00"))
    store.insert_buildable_unit(
        _unit("bu-dev", domain="devtools", category="cli_tool", evidence_signals=["sig-dev"])
    )
    store.insert_buildable_unit(
        _unit("bu-fin", domain="fintech", category="application", evidence_signals=["sig-fin"])
    )

    assert build_opportunity_heatmap(store, domain="devtools")[0]["domain"] == "devtools"
    assert build_opportunity_heatmap(store, min_signals=2) == []


def test_build_opportunity_heatmap_validates_limits(store: Store) -> None:
    try:
        build_opportunity_heatmap(store, min_signals=-1)
    except ValueError as exc:
        assert "min_signals" in str(exc)
    else:
        raise AssertionError("expected min_signals validation error")

    try:
        build_opportunity_heatmap(store, limit=0)
    except ValueError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("expected limit validation error")
