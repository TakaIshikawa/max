"""Tests for insight conversion funnel reports."""

from __future__ import annotations

from datetime import datetime, timezone

from max.analysis.insight_conversion_funnel_report import build_insight_conversion_funnel_report
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory


def test_insight_conversion_funnel_ranks_weak_funnels_first(store: Store) -> None:
    _insight(store, "ins-orphan", InsightCategory.GAP, ["finops"], "2026-05-01T00:00:00+00:00")
    _insight(store, "ins-weak", InsightCategory.TREND, ["support"], "2026-05-02T00:00:00+00:00")
    _insight(store, "ins-healthy", InsightCategory.PAIN_POINT, ["sales"], "2026-05-03T00:00:00+00:00")
    _unit(store, "bu-weak", ["ins-weak"], "draft", "support", "support-profile")
    _unit(store, "bu-healthy", ["ins-healthy"], "published", "sales", "sales-profile")

    report = build_insight_conversion_funnel_report(store, limit=20)
    repeated = build_insight_conversion_funnel_report(store, limit=20)

    assert report == repeated
    assert report["summary"]["insight_count"] == 3
    assert report["summary"]["unit_count"] == 2
    assert report["summary"]["accepted_count"] == 1
    assert [(row["cohort_type"], row["cohort"]) for row in report["funnel_rows"][:2]] == [
        ("category", "gap"),
        ("domain", "finops"),
    ]
    weak = {row["cohort_key"]: row for row in report["funnel_rows"]}
    assert weak["category:gap"]["dropoff_band"] == "no_units"
    assert weak["category:gap"]["insight_count"] == 1
    assert weak["category:gap"]["unit_count"] == 0
    assert weak["category:trend"]["dropoff_band"] == "weak_approval"
    assert weak["category:trend"]["unit_to_accepted_conversion_rate"] == 0.0
    assert weak["category:pain_point"]["published_count"] == 1
    assert weak["category:pain_point"]["dropoff_band"] == "healthy"
    assert any("weak conversion" in action for action in report["next_actions"])


def test_insight_conversion_funnel_reports_missing_lineage_profiles(store: Store) -> None:
    _unit(store, "bu-unlinked", [], "approved", "platform", "platform-profile")

    report = build_insight_conversion_funnel_report(store, limit=10)

    row = {item["cohort_key"]: item for item in report["funnel_rows"]}["profile:platform-profile"]
    assert row["cohort_key"] == "profile:platform-profile"
    assert row["insight_count"] == 0
    assert row["unit_count"] == 1
    assert row["approved_count"] == 1
    assert row["dropoff_band"] == "no_insights"
    assert row["dropoff_stage"] == "missing_insight_lineage"


def test_insight_conversion_funnel_rejects_invalid_limit(store: Store) -> None:
    try:
        build_insight_conversion_funnel_report(store, limit=0)
    except ValueError as exc:
        assert str(exc) == "limit must be at least 1"
    else:
        raise AssertionError("expected ValueError")


def _insight(
    store: Store,
    insight_id: str,
    category: InsightCategory,
    domains: list[str],
    created_at: str,
) -> None:
    store.insert_insight(
        Insight(
            id=insight_id,
            category=category,
            title=insight_id,
            summary=insight_id,
            evidence=[],
            domains=domains,
            created_at=datetime.fromisoformat(created_at),
        )
    )


def _unit(
    store: Store,
    unit_id: str,
    insights: list[str],
    status: str,
    domain: str,
    profile: str,
) -> None:
    store.insert_buildable_unit(
        BuildableUnit(
            id=unit_id,
            title=unit_id,
            one_liner=unit_id,
            category="automation",
            problem="problem",
            solution="solution",
            value_proposition="value",
            inspiring_insights=insights,
            evidence_signals=[],
            domain=domain,
            status=status,
            suggested_stack={"profile": profile},
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
    )
