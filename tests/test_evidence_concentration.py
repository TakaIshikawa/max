"""Tests for portfolio evidence concentration analysis."""

from __future__ import annotations

import pytest

from max.analysis.evidence_concentration import (
    SOURCE_ADAPTER_SHARE_THRESHOLD,
    SIGNAL_ROLE_SHARE_THRESHOLD,
    build_evidence_concentration_report,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _signal(
    signal_id: str,
    *,
    adapter: str,
    tags: list[str],
    role: str,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"Signal {signal_id}",
        content="Evidence concentration fixture",
        url=f"https://example.com/evidence/{signal_id}",
        tags=tags,
        metadata={"signal_role": role},
    )


def _idea(
    idea_id: str,
    *,
    title: str,
    signals: list[str] | None = None,
    insights: list[str] | None = None,
    status: str = "approved",
    domain: str = "devtools",
) -> BuildableUnit:
    return BuildableUnit(
        id=idea_id,
        title=title,
        one_liner=f"{title} one-liner",
        category=BuildableCategory.APPLICATION,
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        evidence_signals=signals or [],
        inspiring_insights=insights or [],
        status=status,
        domain=domain,
    )


def test_evidence_concentration_groups_shares_and_recommendations(store: Store) -> None:
    store.insert_signal(_signal("sig-1", adapter="forum_a", tags=["devtools"], role="problem"))
    store.insert_signal(_signal("sig-2", adapter="forum_a", tags=["devtools"], role="problem"))
    store.insert_signal(_signal("sig-3", adapter="forum_a", tags=["devtools"], role="problem"))
    store.insert_signal(_signal("sig-4", adapter="forum_a", tags=["ai"], role="problem"))
    store.insert_signal(_signal("sig-5", adapter="registry_b", tags=["ai"], role="solution"))
    store.insert_signal(_signal("sig-6", adapter="forum_a", tags=["devtools"], role="problem"))
    store.insert_insight(
        Insight(
            id="ins-1",
            category=InsightCategory.GAP,
            title="Insight",
            summary="Insight summary",
            evidence=["sig-6"],
            confidence=0.8,
            domains=["devtools"],
        )
    )

    store.insert_buildable_unit(
        _idea("bu-1", title="Concentrated idea", signals=["sig-1", "sig-2", "sig-3"])
    )
    store.insert_buildable_unit(
        _idea("bu-2", title="Mixed idea", signals=["sig-4", "sig-5"], status="evaluated")
    )
    store.insert_buildable_unit(
        _idea("bu-3", title="Insight idea", signals=["sig-5"], insights=["ins-1"])
    )
    store.insert_buildable_unit(
        _idea("bu-rejected", title="Rejected idea", signals=["sig-5"], status="rejected")
    )

    report = build_evidence_concentration_report(store, limit=2)

    assert report["total_ideas"] == 3
    assert report["ideas_with_evidence"] == 3
    assert report["total_evidence_links"] == 7

    by_adapter = {row["source_adapter"]: row for row in report["by_source_adapter"]}
    assert by_adapter["forum_a"]["count"] == 5
    assert by_adapter["forum_a"]["share"] == pytest.approx(5 / 7, abs=0.0001)
    assert by_adapter["registry_b"]["count"] == 2

    by_domain_tag = {row["domain_tag"]: row for row in report["by_domain_tag"]}
    assert by_domain_tag["devtools"]["count"] == 4
    assert by_domain_tag["ai"]["count"] == 3

    by_role = {row["signal_role"]: row for row in report["by_signal_role"]}
    assert by_role["problem"]["count"] == 5
    assert by_role["solution"]["count"] == 2

    assert [row["idea_id"] for row in report["top_concentrated_ideas"]] == ["bu-1", "bu-2"]
    assert report["top_concentrated_ideas"][0]["dominant_source_adapter"] == "forum_a"
    assert report["top_concentrated_ideas"][0]["source_adapter_share"] == 1.0

    recs = {(row["dimension"], row["value"]): row for row in report["recommendations"]}
    assert recs[("source_adapter", "forum_a")]["threshold"] == SOURCE_ADAPTER_SHARE_THRESHOLD
    assert recs[("signal_role", "problem")]["threshold"] == SIGNAL_ROLE_SHARE_THRESHOLD


def test_evidence_concentration_empty_store_returns_zero_count_report(store: Store) -> None:
    report = build_evidence_concentration_report(store)

    assert report["total_ideas"] == 0
    assert report["ideas_with_evidence"] == 0
    assert report["total_evidence_links"] == 0
    assert report["by_source_adapter"] == []
    assert report["by_domain_tag"] == []
    assert report["by_signal_role"] == []
    assert report["top_concentrated_ideas"] == []
    assert report["recommendations"] == []


def test_evidence_concentration_rejects_invalid_limit(store: Store) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_evidence_concentration_report(store, limit=0)
