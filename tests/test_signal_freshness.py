"""Tests for signal freshness analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from max.analysis.signal_freshness import (
    SignalFreshnessAnalyzer,
    build_signal_freshness_report,
    render_freshness_markdown,
)
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


def _signal(
    idx: int,
    *,
    adapter: str,
    source_type: SignalSourceType = SignalSourceType.FORUM,
    age_days: int,
    tags: list[str] | None = None,
    role: str = "",
) -> Signal:
    now = datetime(2026, 4, 23, tzinfo=timezone.utc)
    metadata = {"signal_role": role} if role else {}
    return Signal(
        id=f"sig-fresh-{idx:03d}",
        source_type=source_type,
        source_adapter=adapter,
        title=f"Signal {idx}",
        content="Freshness test signal",
        url=f"https://example.com/freshness/{idx}",
        published_at=now - timedelta(days=age_days),
        fetched_at=now - timedelta(days=age_days),
        tags=tags or [],
        metadata=metadata,
    )


def test_signal_freshness_groups_and_recommendations(store: Store) -> None:
    now = datetime(2026, 4, 23, tzinfo=timezone.utc)
    store.insert_signal(
        _signal(1, adapter="hackernews", age_days=2, tags=["devtools"], role="market")
    )
    store.insert_signal(
        _signal(2, adapter="hackernews", age_days=12, tags=["devtools", "ai"], role="market")
    )
    store.insert_signal(
        _signal(
            3,
            adapter="npm_registry",
            source_type=SignalSourceType.REGISTRY,
            age_days=20,
            tags=["devtools"],
            role="solution",
        )
    )

    report = build_signal_freshness_report(store, max_age_days=10, now=now)

    assert report.total_signals == 3
    assert report.stale_signals == 2
    by_adapter = {item.key: item for item in report.by_source_adapter}
    assert by_adapter["hackernews"].total_count == 2
    assert by_adapter["hackernews"].stale_count == 1
    assert by_adapter["hackernews"].median_age_days == 7.0
    by_tag = {item.key: item for item in report.by_domain_tag}
    assert by_tag["devtools"].total_count == 3
    assert by_tag["ai"].total_count == 1
    assert [rec.source_adapter for rec in report.recommendations] == [
        "npm_registry",
        "hackernews",
    ]


def test_signal_freshness_filters_source_adapter_and_ignores_archived(store: Store) -> None:
    now = datetime(2026, 4, 23, tzinfo=timezone.utc)
    store.insert_signal(_signal(1, adapter="hackernews", age_days=2, tags=["devtools"]))
    store.insert_signal(_signal(2, adapter="reddit", age_days=30, tags=["community"]))
    store.archive_signal("sig-fresh-002")

    report = build_signal_freshness_report(
        store,
        max_age_days=10,
        source_adapters=["hackernews", "reddit"],
        now=now,
    )

    assert report.source_adapter_filters == ["hackernews", "reddit"]
    assert report.total_signals == 1
    assert report.by_source_adapter[0].key == "hackernews"


def test_analyzer_computes_age_from_fetched_or_published_timestamp() -> None:
    analyzer = SignalFreshnessAnalyzer(staleness_threshold_hours=24)
    now = datetime(2026, 4, 23, 12, tzinfo=timezone.utc)

    fetched_age = analyzer._compute_age(
        {
            "published_at": now - timedelta(hours=20),
            "fetched_at": now - timedelta(hours=6),
        },
        now,
    )
    published_age = analyzer._compute_age(
        {"published_at": (now - timedelta(hours=9)).isoformat()},
        now,
    )

    assert fetched_age == 6
    assert published_age == 9


def test_analyzer_health_classification_thresholds() -> None:
    analyzer = SignalFreshnessAnalyzer(staleness_threshold_hours=100)

    assert analyzer._classify_health(avg_age=20, stale_ratio=0) == "fresh"
    assert analyzer._classify_health(avg_age=60, stale_ratio=0) == "aging"
    assert analyzer._classify_health(avg_age=110, stale_ratio=0.2) == "stale"
    assert analyzer._classify_health(avg_age=50, stale_ratio=0.8) == "critical"


def test_analyzer_groups_by_source_adapter() -> None:
    now = datetime.now(timezone.utc)
    analyzer = SignalFreshnessAnalyzer(staleness_threshold_hours=24)

    report = analyzer.analyze(
        [
            {
                "source_adapter": "hackernews",
                "fetched_at": now - timedelta(hours=2),
            },
            {
                "source_adapter": "hackernews",
                "fetched_at": now - timedelta(hours=30),
            },
            {
                "source_adapter": "npm_registry",
                "published_at": now - timedelta(hours=4),
            },
        ]
    )

    by_adapter = {score.source_adapter: score for score in report.scores}
    assert by_adapter["hackernews"].signal_count == 2
    assert by_adapter["hackernews"].stale_count == 1
    assert by_adapter["hackernews"].stale_ratio == 0.5
    assert by_adapter["npm_registry"].signal_count == 1
    assert by_adapter["npm_registry"].health == "fresh"


def test_analyzer_overall_health_uses_worst_score() -> None:
    now = datetime.now(timezone.utc)
    analyzer = SignalFreshnessAnalyzer(staleness_threshold_hours=24)

    report = analyzer.analyze(
        [
            {"source_adapter": "fresh_source", "fetched_at": now - timedelta(hours=1)},
            {"source_adapter": "old_source", "fetched_at": now - timedelta(hours=80)},
        ]
    )

    assert report.overall_health == "critical"


def test_analyzer_all_fresh_signals() -> None:
    now = datetime.now(timezone.utc)
    analyzer = SignalFreshnessAnalyzer(staleness_threshold_hours=24)

    report = analyzer.analyze(
        [
            {"source_adapter": "hackernews", "fetched_at": now - timedelta(hours=1)},
            {"source_adapter": "hackernews", "fetched_at": now - timedelta(hours=2)},
        ]
    )

    assert report.overall_health == "fresh"
    assert report.scores[0].stale_count == 0
    assert report.scores[0].health == "fresh"


def test_analyzer_all_stale_signals() -> None:
    now = datetime.now(timezone.utc)
    analyzer = SignalFreshnessAnalyzer(staleness_threshold_hours=24)

    report = analyzer.analyze(
        [
            {"source_adapter": "hackernews", "fetched_at": now - timedelta(hours=30)},
            {"source_adapter": "hackernews", "fetched_at": now - timedelta(hours=36)},
        ]
    )

    assert report.overall_health == "critical"
    assert report.scores[0].stale_count == 2
    assert report.scores[0].stale_ratio == 1.0


def test_analyzer_empty_signal_list() -> None:
    report = SignalFreshnessAnalyzer().analyze([])

    assert report.scores == []
    assert report.overall_health == "fresh"
    assert report.staleness_threshold_hours == 168.0


def test_render_freshness_markdown() -> None:
    now = datetime.now(timezone.utc)
    report = SignalFreshnessAnalyzer(staleness_threshold_hours=24).analyze(
        [{"source_adapter": "hackernews", "fetched_at": now - timedelta(hours=2)}]
    )

    markdown = render_freshness_markdown(report)

    assert markdown.startswith("# Signal Freshness")
    assert (
        "| Source | Count | Avg age | Median age | Newest | Oldest | Stale | Health |"
        in markdown
    )
    assert "hackernews" in markdown
    assert "[green] fresh" in markdown
