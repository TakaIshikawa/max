"""Tests for signal freshness analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from max.analysis.signal_freshness import build_signal_freshness_report
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
