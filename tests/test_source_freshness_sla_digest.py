from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from io import StringIO

import pytest

from max.analysis.source_freshness_sla_digest import (
    KIND,
    SCHEMA_VERSION,
    build_source_freshness_sla_digest,
    render_source_freshness_sla_digest,
)
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


def test_source_freshness_sla_digest_ranks_stale_sources_first(store: Store) -> None:
    _seed_signals(store)

    report = build_source_freshness_sla_digest(
        store,
        stale_after_hours=24,
        now=datetime(2026, 5, 20, tzinfo=UTC),
    )
    repeated = build_source_freshness_sla_digest(
        store,
        stale_after_hours=24,
        now=datetime(2026, 5, 20, tzinfo=UTC),
    )

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert set(report) == {
        "schema_version",
        "kind",
        "filters",
        "summary",
        "adapters",
        "freshness_bands",
        "next_actions",
    }
    assert [row["adapter"] for row in report["adapters"]] == ["stale_adapter", "fresh_adapter", "aging_adapter"]
    rows = {row["adapter"]: row for row in report["adapters"]}
    assert rows["stale_adapter"]["freshness_band"] == "stale"
    assert rows["stale_adapter"]["newest_age_hours"] == 96.0
    assert rows["aging_adapter"]["freshness_band"] == "aging"
    assert rows["fresh_adapter"]["freshness_band"] == "fresh"
    assert report["freshness_bands"]["stale"] == ["stale_adapter"]
    assert report["summary"]["stale_signal_count"] == 3


def test_source_freshness_sla_digest_limit_and_renderers(store: Store) -> None:
    _seed_signals(store)
    report = build_source_freshness_sla_digest(
        store,
        stale_after_hours=24,
        limit=2,
        now=datetime(2026, 5, 20, tzinfo=UTC),
    )

    assert [row["adapter"] for row in report["adapters"]] == ["stale_adapter", "fresh_adapter"]
    assert json.loads(render_source_freshness_sla_digest(report, fmt="json")) == report
    markdown = render_source_freshness_sla_digest(report, fmt="markdown")
    assert markdown.startswith("# Source Freshness SLA Digest")
    rows = list(csv.DictReader(StringIO(render_source_freshness_sla_digest(report, fmt="csv"))))
    assert rows[0]["adapter"] == "stale_adapter"

    with pytest.raises(ValueError, match="stale_after_hours must be greater than 0"):
        build_source_freshness_sla_digest(store, stale_after_hours=0)
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_source_freshness_sla_digest(store, limit=0)
    with pytest.raises(ValueError, match="Unsupported source freshness SLA digest format: yaml"):
        render_source_freshness_sla_digest(report, fmt="yaml")


def _seed_signals(store: Store) -> None:
    _signal(store, "sig-stale-1", "stale_adapter", "2026-05-16T00:00:00+00:00")
    _signal(store, "sig-stale-2", "stale_adapter", "2026-05-15T00:00:00+00:00")
    _signal(store, "sig-fresh", "fresh_adapter", "2026-05-19T12:00:00+00:00")
    _signal(store, "sig-aging-old", "aging_adapter", "2026-05-10T00:00:00+00:00")
    _signal(store, "sig-aging-new", "aging_adapter", "2026-05-19T18:00:00+00:00")


def _signal(store: Store, signal_id: str, adapter: str, fetched_at: str) -> None:
    store.insert_signal(
        Signal(
            id=signal_id,
            source_type=SignalSourceType.FORUM,
            source_adapter=adapter,
            title=signal_id,
            content="content",
            url=f"https://example.com/{signal_id}",
        )
    )
    store.conn.execute(
        "UPDATE signals SET fetched_at = ?, published_at = NULL WHERE id = ?",
        (fetched_at, signal_id),
    )
    store._commit()
