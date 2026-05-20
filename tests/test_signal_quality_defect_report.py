"""Tests for signal quality defect reports."""

from __future__ import annotations

from datetime import datetime, timezone

from max.analysis.signal_quality_defect_report import build_signal_quality_defect_report
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


def test_signal_quality_defect_report_counts_and_ranks_defects(store: Store) -> None:
    _signal(store, "sig-good", "hackernews", "Good", "Body", "https://example.com/good")
    _signal(store, "sig-missing", "hackernews", "", "", "")
    _signal(store, "sig-unknown", "mystery", "Unknown", "Body", "https://example.com/unknown")
    _signal(store, "sig-dup-a", "reddit", "Dup A", "Body", "https://example.com/dup")
    _signal(store, "sig-dup-b", "hackernews", "Dup B", "Body", "https://example.com/dup-b")
    store.conn.execute("DROP INDEX IF EXISTS idx_signals_url")
    store.conn.execute("UPDATE signals SET url = ? WHERE id = ?", ("https://example.com/dup", "sig-dup-b"))
    store.conn.execute("UPDATE signals SET fetched_at = ? WHERE id = ?", ("not-a-date", "sig-missing"))
    store._commit()

    report = build_signal_quality_defect_report(store, limit=20)
    repeated = build_signal_quality_defect_report(store, limit=20)

    assert report == repeated
    assert report["summary"]["signal_count"] == 5
    assert report["summary"]["critical_defect_count"] == 4
    assert report["adapters"][0]["adapter"] == "hackernews"
    assert report["adapters"][0]["highest_severity"] == "critical"
    assert report["adapters"][0]["defects_by_type"]["missing_url"] == 1
    assert report["adapters"][0]["defects_by_type"]["duplicate_url"] == 1
    assert "reddit" in report["defect_bands"]["critical"]
    assert "mystery" in report["defect_bands"]["warning"]
    duplicate_defects = [item for item in report["defects"] if item["defect_type"] == "duplicate_url"]
    assert {item["adapter"] for item in duplicate_defects} == {"hackernews", "reddit"}
    assert any("critical signal" in action for action in report["next_actions"])


def test_signal_quality_defect_report_marks_clean_adapters(store: Store) -> None:
    _signal(store, "sig-good", "hackernews", "Good", "Body", "https://example.com/good")

    report = build_signal_quality_defect_report(store)

    assert report["summary"]["defect_count"] == 0
    assert report["adapters"] == [
        {
            "adapter": "hackernews",
            "signal_count": 1,
            "defect_count": 0,
            "critical_count": 0,
            "warning_count": 0,
            "defects_by_type": {},
            "highest_severity": "clean",
        }
    ]
    assert report["defect_bands"]["clean"] == ["hackernews"]


def test_signal_quality_defect_report_rejects_invalid_limit(store: Store) -> None:
    try:
        build_signal_quality_defect_report(store, limit=0)
    except ValueError as exc:
        assert str(exc) == "limit must be at least 1"
    else:
        raise AssertionError("expected ValueError")


def _signal(store: Store, signal_id: str, adapter: str, title: str, content: str, url: str) -> None:
    store.insert_signal(
        Signal(
            id=signal_id,
            source_type=SignalSourceType.FORUM,
            source_adapter=adapter,
            title=title,
            content=content,
            url=url,
            fetched_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
    )
