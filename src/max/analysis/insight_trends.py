"""Insight trend aggregation for repeated category/domain combinations."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from max.store.db import Store
from max.types.insight import Insight


@dataclass(frozen=True)
class InsightTrend:
    """Aggregate metrics for one category/domain/time horizon group."""

    category: str
    domain: str
    time_horizon: str
    count: int
    average_confidence: float
    newest_insight_at: datetime
    top_evidence_signal_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InsightTrendSummary:
    """Filtered insight trend result set."""

    days: int | None
    domain: str | None
    category: str | None
    total_insights: int
    trends: list[InsightTrend]


def _as_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def group_insight_trends(
    insights: list[Insight],
    *,
    top_evidence_limit: int = 5,
) -> list[InsightTrend]:
    """Group insights by category, domain, and time horizon.

    Insights with multiple domains contribute to each domain group. Insights
    without domains do not form a category/domain combination.
    """
    groups: dict[tuple[str, str, str], list[Insight]] = {}
    for insight in insights:
        category = insight.category.value if hasattr(insight.category, "value") else str(insight.category)
        for domain in insight.domains:
            key = (category, domain, insight.time_horizon)
            groups.setdefault(key, []).append(insight)

    trends: list[InsightTrend] = []
    for (category, domain, time_horizon), group in groups.items():
        evidence_counts: Counter[str] = Counter()
        for insight in group:
            evidence_counts.update(insight.evidence)

        top_evidence = [
            signal_id
            for signal_id, _count in sorted(
                evidence_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:top_evidence_limit]
        ]
        newest = max(_as_aware_datetime(insight.created_at) for insight in group)
        trends.append(
            InsightTrend(
                category=category,
                domain=domain,
                time_horizon=time_horizon,
                count=len(group),
                average_confidence=sum(insight.confidence for insight in group) / len(group),
                newest_insight_at=newest,
                top_evidence_signal_ids=top_evidence,
            )
        )

    return sorted(
        trends,
        key=lambda trend: (
            -trend.count,
            -trend.average_confidence,
            -trend.newest_insight_at.timestamp(),
            trend.category,
            trend.domain,
            trend.time_horizon,
        ),
    )


def analyze_insight_trends(
    store: Store,
    *,
    domain: str | None = None,
    category: str | None = None,
    days: int | None = None,
    limit: int = 20,
    now: datetime | None = None,
) -> InsightTrendSummary:
    """Load active insights from storage and aggregate category/domain trends."""
    if days is not None and days < 1:
        raise ValueError("days must be at least 1")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    cutoff = None
    if days is not None:
        end = _as_aware_datetime(now or datetime.now(UTC))
        cutoff = end - timedelta(days=days)

    insights = store.get_active_insights(
        domain=domain,
        category=category,
        created_since=cutoff.isoformat() if cutoff else None,
    )
    trends = group_insight_trends(insights)
    if domain:
        trends = [trend for trend in trends if trend.domain == domain]
    trends = trends[:limit]
    return InsightTrendSummary(
        days=days,
        domain=domain,
        category=category,
        total_insights=len(insights),
        trends=trends,
    )
