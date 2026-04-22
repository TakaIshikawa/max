"""Tests for source reliability analysis."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from max.analysis.source_reliability import build_source_reliability_report
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _signal(
    signal_id: str,
    adapter: str,
    source_type: SignalSourceType,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=adapter,
        title="Shared market pain",
        content="Developers report the same operational pain across sources.",
        url=f"https://example.com/{signal_id}",
        credibility=0.8,
    )


def test_source_reliability_empty_store(store: Store) -> None:
    report = build_source_reliability_report(store)

    assert report.total_signals == 0
    assert report.source_types == []


def test_source_reliability_scores_by_source_type(store: Store) -> None:
    hn = _signal("sig-hn", "hackernews", SignalSourceType.FORUM)
    reddit = _signal("sig-reddit", "reddit", SignalSourceType.FORUM)
    npm = _signal("sig-npm", "npm_registry", SignalSourceType.REGISTRY)
    store.insert_signal(hn)
    store.insert_signal(reddit)
    store.insert_signal(npm)

    store.insert_insight(
        Insight(
            id="ins-1",
            category=InsightCategory.GAP,
            title="Shared pain",
            summary="Forum evidence shows a repeat pain.",
            evidence=["sig-hn"],
            confidence=0.8,
        )
    )
    store.insert_buildable_unit(
        BuildableUnit(
            id="bu-1",
            title="Idea",
            one_liner="Idea",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Problem",
            solution="Solution",
            target_users="both",
            value_proposition="Value",
            evidence_signals=["sig-hn", "sig-reddit"],
        )
    )
    store.insert_feedback("bu-1", "approved")
    store.insert_pipeline_run("run-1", {})
    store.update_pipeline_run(
        "run-1",
        adapter_metrics={
            "hackernews": {"status": "ok"},
            "reddit": {"status": "ok"},
            "npm_registry": {"status": "error"},
        },
    )

    clusters = [SimpleNamespace(signals=[hn, reddit])]
    with (
        patch(
            "max.analysis.source_reliability.list_adapters",
            return_value=["hackernews", "reddit", "npm_registry"],
        ),
        patch(
            "max.analysis.source_reliability.snapshot_circuit_breakers",
            return_value=[
                SimpleNamespace(adapter_name="hackernews", state="closed"),
                SimpleNamespace(adapter_name="reddit", state="closed"),
                SimpleNamespace(adapter_name="npm_registry", state="closed"),
            ],
        ),
        patch("max.analysis.source_reliability.triangulate", return_value=clusters),
    ):
        report = build_source_reliability_report(store)

    by_type = {row.source_type: row for row in report.source_types}
    assert set(by_type) == {"forum", "registry"}
    assert by_type["forum"].total_signals == 2
    assert by_type["forum"].adapter_health_score == 1.0
    assert by_type["forum"].signal_usefulness_score == pytest.approx(0.5)
    assert by_type["forum"].corroboration_rate == 1.0
    assert by_type["forum"].downstream_idea_conversion_rate == 1.0
    assert by_type["forum"].feedback_approval_rate == 1.0
    assert by_type["forum"].reliability_score == pytest.approx(0.85)
    assert by_type["registry"].adapter_health_score == pytest.approx(2 / 3, abs=0.0001)
    assert by_type["registry"].reliability_score == pytest.approx(0.1667)
    assert by_type["forum"].reasons
