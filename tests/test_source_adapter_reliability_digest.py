"""Tests for source adapter reliability digest generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.source_adapter_reliability_digest import (
    KIND,
    SCHEMA_VERSION,
    build_source_adapter_reliability_digest,
    render_source_adapter_reliability_digest,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def test_build_source_adapter_reliability_digest_ranks_adapter_bands(store: Store) -> None:
    _seed_runs(store)
    _seed_signals_and_utilization(store)

    report = build_source_adapter_reliability_digest(store, limit=10, min_runs=1)
    repeated = build_source_adapter_reliability_digest(store, limit=10, min_runs=1)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["run_count"] == 3
    assert report["summary"]["adapter_count"] == 3
    assert report["reliability_bands"] == {
        "failing": ["broken_adapter"],
        "low_yield": ["low_yield_adapter"],
        "watch": [],
        "healthy": ["healthy_adapter"],
    }
    assert [row["adapter"] for row in report["adapters"]] == [
        "broken_adapter",
        "low_yield_adapter",
        "healthy_adapter",
    ]

    rows = {row["adapter"]: row for row in report["adapters"]}
    assert rows["healthy_adapter"]["run_count"] == 3
    assert rows["healthy_adapter"]["success_count"] == 3
    assert rows["healthy_adapter"]["failure_count"] == 0
    assert rows["healthy_adapter"]["average_fetched_signals"] == pytest.approx(5.0)
    assert rows["healthy_adapter"]["utilization"]["insight_hit_rate"] == pytest.approx(0.5)
    assert rows["healthy_adapter"]["utilization"]["idea_hit_rate"] == pytest.approx(0.5)

    assert rows["broken_adapter"]["success_count"] == 0
    assert rows["broken_adapter"]["failure_count"] == 3
    assert rows["broken_adapter"]["last_error"] == "HTTP 500"
    assert rows["broken_adapter"]["reliability_band"] == "failing"
    assert any("Repair `broken_adapter`" in item for item in rows["broken_adapter"]["recommendations"])

    assert rows["low_yield_adapter"]["reliability_band"] == "low_yield"
    assert rows["low_yield_adapter"]["average_fetched_signals"] == pytest.approx(1.0)
    assert any("Reduce allocation" in item for item in report["next_actions"])


def test_source_adapter_reliability_digest_min_runs_filters_adapters(store: Store) -> None:
    _seed_runs(store)

    report = build_source_adapter_reliability_digest(store, limit=10, min_runs=3)

    assert [row["adapter"] for row in report["adapters"]] == [
        "broken_adapter",
        "healthy_adapter",
    ]
    assert report["summary"]["excluded_below_min_runs_count"] == 1


def test_source_adapter_reliability_digest_no_data_returns_empty_report(store: Store) -> None:
    report = build_source_adapter_reliability_digest(store)

    assert report["adapters"] == []
    assert report["summary"]["run_count"] == 0
    assert report["summary"]["adapter_count"] == 0
    assert report["next_actions"] == [
        "Run the pipeline with adapter metrics enabled, then synthesize signals to populate utilization stats."
    ]


def test_render_source_adapter_reliability_digest_json_markdown_and_invalid_format(
    store: Store,
) -> None:
    _seed_runs(store)
    _seed_signals_and_utilization(store)
    report = build_source_adapter_reliability_digest(store, limit=10, min_runs=1)

    rendered_json = render_source_adapter_reliability_digest(report, fmt="json")
    assert json.loads(rendered_json) == report

    markdown = render_source_adapter_reliability_digest(report, fmt="markdown")
    assert markdown.startswith("# Source Adapter Reliability Digest")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Adapter Rankings" in markdown
    assert "| `broken_adapter` | failing |" in markdown
    assert "## Follow-Up Actions" in markdown

    with pytest.raises(ValueError, match="Unsupported source adapter reliability digest format: yaml"):
        render_source_adapter_reliability_digest(report, fmt="yaml")


def test_source_adapter_reliability_digest_validates_arguments(store: Store) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_source_adapter_reliability_digest(store, limit=0)
    with pytest.raises(ValueError, match="min_runs must be at least 1"):
        build_source_adapter_reliability_digest(store, min_runs=0)


def _seed_runs(store: Store) -> None:
    for index in range(3):
        run_id = f"run-reliability-{index}"
        store.insert_pipeline_run(run_id, {"signal_limit": 20})
        store.update_pipeline_run(
            run_id,
            signals_fetched=5 if index else 6,
            adapter_metrics={
                "healthy_adapter": {
                    "status": "ok",
                    "signal_count": 5,
                    "error_message": None,
                    "duration_ms": 100 + index,
                },
                "broken_adapter": {
                    "status": "error",
                    "signal_count": 0,
                    "error_message": "HTTP 500" if index == 2 else "timeout",
                    "duration_ms": 500,
                },
                **(
                    {
                        "low_yield_adapter": {
                            "status": "ok",
                            "signal_count": 1,
                            "error_message": None,
                            "duration_ms": 80,
                        }
                    }
                    if index == 1
                    else {}
                ),
            },
        )


def _seed_signals_and_utilization(store: Store) -> None:
    for index in range(2):
        store.insert_signal(_signal("healthy_adapter", index))
    store.insert_signal(_signal("low_yield_adapter", 0))

    store.insert_insight(
        Insight(
            id="ins-reliability-healthy",
            category=InsightCategory.GAP,
            title="Healthy source insight",
            summary="Healthy adapter evidence is useful.",
            evidence=["sig-healthy_adapter-0"],
            confidence=0.8,
            domains=["reliability"],
            implications=[],
            time_horizon="near_term",
        )
    )
    store.insert_buildable_unit(
        BuildableUnit(
            id="bu-reliability-healthy",
            title="Healthy source idea",
            one_liner="Use healthy source evidence.",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Operators need adapter reliability.",
            solution="Rank adapters by run and utilization health.",
            target_users="operators",
            value_proposition="Faster source repair decisions.",
            evidence_signals=["sig-healthy_adapter-1"],
        )
    )


def _signal(adapter: str, index: int) -> Signal:
    return Signal(
        id=f"sig-{adapter}-{index}",
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"{adapter} signal {index}",
        content="Adapter reliability evidence.",
        url=f"https://example.com/{adapter}/{index}",
        credibility=0.7,
    )
