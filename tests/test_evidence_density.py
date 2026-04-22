"""Tests for idea evidence density analysis."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from max.analysis.evidence_density import build_evidence_density_report
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def store():
    s = Store(db_path=":memory:")
    yield s
    s.close()


def _signal(
    signal_id: str,
    *,
    adapter: str,
    source_type: SignalSourceType,
    role: str,
    credibility: float,
    published_at: datetime | None = None,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=adapter,
        title=f"Signal {signal_id}",
        content="Evidence content",
        url=f"https://example.com/{signal_id}",
        credibility=credibility,
        published_at=published_at,
        fetched_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
        metadata={"signal_role": role},
    )


def _idea(
    *,
    insights: list[str] | None = None,
    signals: list[str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id="bu-density",
        title="Density Idea",
        one_liner="A density test idea",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Need evidence density",
        solution="Compute it",
        value_proposition="Clearer review",
        inspiring_insights=insights or [],
        evidence_signals=signals or [],
    )


def test_evidence_density_counts_quality_timestamps_and_score(store):
    store.insert_signal(
        _signal(
            "sig-1",
            adapter="github",
            source_type=SignalSourceType.REGISTRY,
            role="problem",
            credibility=0.8,
            published_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        )
    )
    store.insert_signal(
        _signal(
            "sig-2",
            adapter="reddit",
            source_type=SignalSourceType.FORUM,
            role="market",
            credibility=0.6,
            published_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        )
    )
    store.insert_insight(
        Insight(
            id="ins-1",
            category=InsightCategory.GAP,
            title="Insight",
            summary="Two pieces of evidence support the idea.",
            evidence=["sig-1", "sig-2"],
            confidence=0.8,
        )
    )

    report = build_evidence_density_report(_idea(insights=["ins-1"], signals=["sig-2"]), store)

    assert report["signal_count"] == 2
    assert report["insight_count"] == 1
    assert report["counts_by_source_adapter"] == {"github": 1, "reddit": 1}
    assert report["counts_by_source_type"] == {"forum": 1, "registry": 1}
    assert report["counts_by_signal_role"] == {"market": 1, "problem": 1}
    assert report["average_credibility"] == 0.7
    assert report["oldest_evidence_timestamp"] == "2026-04-20T00:00:00+00:00"
    assert report["newest_evidence_timestamp"] == "2026-04-21T00:00:00+00:00"
    assert report["missing_evidence_warnings"] == []
    assert report["density_score"] > 0


def test_evidence_density_reports_missing_references(store):
    report = build_evidence_density_report(
        _idea(insights=["ins-missing"], signals=["sig-missing"]),
        store,
    )

    assert report["signal_count"] == 0
    assert report["insight_count"] == 0
    assert report["missing_insight_ids"] == ["ins-missing"]
    assert report["missing_signal_ids"] == ["sig-missing"]
    assert "Missing inspiring insight(s): ins-missing" in report["missing_evidence_warnings"]
    assert "Missing evidence signal(s): sig-missing" in report["missing_evidence_warnings"]
    assert "No evidence signals resolved for this idea." in report["missing_evidence_warnings"]
