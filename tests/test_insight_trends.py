"""Tests for insight category/domain trend aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from max.analysis.insight_trends import analyze_insight_trends, group_insight_trends
from max.store.db import Store
from max.types.insight import Insight, InsightCategory


def _insight(
    insight_id: str,
    *,
    category: InsightCategory = InsightCategory.GAP,
    domains: list[str] | None = None,
    time_horizon: str = "near_term",
    confidence: float = 0.5,
    evidence: list[str] | None = None,
    created_at: datetime | None = None,
) -> Insight:
    return Insight(
        id=insight_id,
        category=category,
        title=f"Insight {insight_id}",
        summary="Summary",
        evidence=evidence or [],
        confidence=confidence,
        domains=domains or ["devtools"],
        implications=[],
        time_horizon=time_horizon,
        created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_group_insight_trends_groups_by_category_domain_and_horizon() -> None:
    insights = [
        _insight("ins-1", domains=["devtools", "ai"], time_horizon="near_term"),
        _insight("ins-2", domains=["devtools"], time_horizon="near_term"),
        _insight("ins-3", domains=["devtools"], time_horizon="long_term"),
    ]

    trends = group_insight_trends(insights)

    assert [(trend.domain, trend.time_horizon, trend.count) for trend in trends] == [
        ("devtools", "near_term", 2),
        ("ai", "near_term", 1),
        ("devtools", "long_term", 1),
    ]


def test_group_insight_trends_averages_confidence_and_ranks_evidence() -> None:
    insights = [
        _insight("ins-1", confidence=0.6, evidence=["sig-1", "sig-2"]),
        _insight("ins-2", confidence=0.9, evidence=["sig-1", "sig-3"]),
        _insight("ins-3", confidence=0.75, evidence=["sig-2", "sig-1"]),
    ]

    trend = group_insight_trends(insights, top_evidence_limit=2)[0]

    assert trend.average_confidence == pytest.approx(0.75)
    assert trend.top_evidence_signal_ids == ["sig-1", "sig-2"]


def test_analyze_insight_trends_filters_active_insights_by_domain_category_and_days(
    store: Store,
) -> None:
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    keep_1 = _insight(
        "ins-keep-1",
        category=InsightCategory.TREND,
        domains=["devtools"],
        confidence=0.8,
        created_at=now - timedelta(days=1),
    )
    keep_2 = _insight(
        "ins-keep-2",
        category=InsightCategory.TREND,
        domains=["devtools", "ai"],
        confidence=0.6,
        created_at=now - timedelta(days=2),
    )
    old = _insight(
        "ins-old",
        category=InsightCategory.TREND,
        domains=["devtools"],
        created_at=now - timedelta(days=10),
    )
    wrong_domain = _insight(
        "ins-domain",
        category=InsightCategory.TREND,
        domains=["healthcare"],
        created_at=now - timedelta(days=1),
    )
    archived = _insight(
        "ins-archived",
        category=InsightCategory.TREND,
        domains=["devtools"],
        created_at=now - timedelta(days=1),
    )
    for insight in [keep_1, keep_2, old, wrong_domain, archived]:
        store.insert_insight(insight)
    store.archive_insight("ins-archived")

    summary = analyze_insight_trends(
        store,
        domain="devtools",
        category="trend",
        days=7,
        now=now,
    )

    assert summary.total_insights == 2
    assert len(summary.trends) == 1
    assert summary.trends[0].domain == "devtools"
    assert summary.trends[0].category == "trend"
    assert summary.trends[0].count == 2
    assert summary.trends[0].average_confidence == pytest.approx(0.7)
