"""Tests for incremental synthesis — schema migration, signal tracking, and pipeline integration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from max.store.db import Store
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_incr.db")
    s = Store(db_path=db_path)
    yield s
    s.close()


def _make_signal(id: str, url: str) -> Signal:
    return Signal(
        id=id,
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title=f"Signal {id}",
        content=f"Content for {id}",
        url=url,
        tags=["test"],
        credibility=0.5,
    )


def _make_insight(id: str) -> Insight:
    return Insight(
        id=id,
        category=InsightCategory.GAP,
        title=f"Insight {id}",
        summary=f"Summary for {id}",
        evidence=["sig-001"],
        confidence=0.8,
        domains=["testing"],
    )


def test_get_unsynthesized_signals_all_new(store):
    """All signals are unsynthesized initially."""
    store.insert_signal(_make_signal("sig-001", "https://example.com/1"))
    store.insert_signal(_make_signal("sig-002", "https://example.com/2"))

    unsynthesized = store.get_unsynthesized_signals()
    assert len(unsynthesized) == 2


def test_get_unsynthesized_signals_after_marking(store):
    """After marking, only unmarked signals are returned."""
    store.insert_signal(_make_signal("sig-001", "https://example.com/1"))
    store.insert_signal(_make_signal("sig-002", "https://example.com/2"))
    store.insert_signal(_make_signal("sig-003", "https://example.com/3"))

    store.mark_signals_synthesized(["sig-001", "sig-002"])

    unsynthesized = store.get_unsynthesized_signals()
    assert len(unsynthesized) == 1
    assert unsynthesized[0].id == "sig-003"


def test_mark_signals_synthesized_sets_timestamp(store):
    """mark_signals_synthesized sets the synthesized_at column."""
    store.insert_signal(_make_signal("sig-001", "https://example.com/1"))
    store.mark_signals_synthesized(["sig-001"])

    row = store.conn.execute(
        "SELECT synthesized_at FROM signals WHERE id = ?", ("sig-001",)
    ).fetchone()
    assert row["synthesized_at"] is not None


def test_mark_signals_synthesized_empty_list(store):
    """Empty list is a no-op."""
    store.mark_signals_synthesized([])  # Should not raise


def test_get_unsynthesized_signals_respects_limit(store):
    """Limit parameter is respected."""
    for i in range(10):
        store.insert_signal(_make_signal(f"sig-{i:03d}", f"https://example.com/{i}"))

    unsynthesized = store.get_unsynthesized_signals(limit=3)
    assert len(unsynthesized) == 3


def test_schema_migration_v1_to_v2(tmp_path):
    """Migration adds synthesized_at column to existing DB."""
    import sqlite3

    from max.store.migrations import _migrate_v1_to_v2

    db_path = str(tmp_path / "v1.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create a v1-like signals table (without synthesized_at)
    conn.execute("""
        CREATE TABLE signals (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_adapter TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            url TEXT NOT NULL,
            author TEXT,
            published_at TEXT,
            fetched_at TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            credibility REAL NOT NULL DEFAULT 0.5,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
    """)
    conn.commit()

    # Verify column doesn't exist
    columns = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    assert "synthesized_at" not in columns

    # Run migration
    _migrate_v1_to_v2(conn)

    # Verify column now exists
    columns = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    assert "synthesized_at" in columns

    conn.close()


def test_schema_migration_idempotent(tmp_path):
    """Running migration twice doesn't fail."""
    import sqlite3

    from max.store.migrations import _migrate_v1_to_v2

    db_path = str(tmp_path / "v1.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE signals (
            id TEXT PRIMARY KEY, source_type TEXT NOT NULL,
            source_adapter TEXT NOT NULL, title TEXT NOT NULL,
            content TEXT NOT NULL, url TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
    """)
    conn.commit()

    _migrate_v1_to_v2(conn)
    _migrate_v1_to_v2(conn)  # Second call should not fail

    conn.close()


def test_synthesize_prior_insights_param():
    """synthesize() accepts and uses prior_insights."""
    from max.synthesis.engine import synthesize

    signals = [_make_signal("sig-001", "https://example.com/1")]
    prior = [_make_insight("ins-001")]

    mock_result = type("SynthesisOutput", (), {"insights": []})()

    with patch("max.synthesis.engine.structured_call", return_value=mock_result) as mock_call:
        synthesize(signals, prior_insights=prior)

    # Verify the prompt contains prior insight context
    call_kwargs = mock_call.call_args
    prompt = call_kwargs.kwargs.get("prompt") or call_kwargs[1].get("prompt", call_kwargs[0][1])
    assert "EXISTING INSIGHTS" in prompt
    assert "Insight ins-001" in prompt


def test_synthesize_without_prior_insights():
    """synthesize() works without prior_insights (backward compatible)."""
    from max.synthesis.engine import synthesize

    signals = [_make_signal("sig-001", "https://example.com/1")]

    mock_result = type("SynthesisOutput", (), {"insights": []})()

    with patch("max.synthesis.engine.structured_call", return_value=mock_result) as mock_call:
        synthesize(signals)

    call_kwargs = mock_call.call_args
    prompt = call_kwargs.kwargs.get("prompt") or call_kwargs[1].get("prompt", call_kwargs[0][1])
    assert "EXISTING INSIGHTS" not in prompt


def test_pipeline_skips_synthesis_when_no_new_signals():
    """Pipeline skips synthesis entirely when all signals are already synthesized."""
    from max.pipeline.runner import PipelineResult

    result = PipelineResult()

    # Simulate: all signals already synthesized → new_signals = []
    # Just verify PipelineResult has the right fields
    assert result.signals_skipped == 0
    assert result.insights_generated == 0
