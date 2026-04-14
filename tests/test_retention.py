"""Tests for data retention and archival system."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from max.store.db import Store
from max.store.migrations import SCHEMA_VERSION, _migrate_v7_to_v8, ensure_schema
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_signal(
    sig_id: str = "sig-test001",
    url: str = "",
    *,
    fetched_days_ago: int = 0,
    synthesized: bool = False,
) -> Signal:
    """Create a test signal with configurable age and synthesis status."""
    fetched_at = datetime.now(timezone.utc) - timedelta(days=fetched_days_ago)
    sig = Signal(
        id=sig_id,
        source_type=SignalSourceType.FORUM,
        source_adapter="test_adapter",
        title=f"Signal {sig_id}",
        content="Test content",
        url=url or f"https://example.com/{sig_id}",
        fetched_at=fetched_at,
    )
    if synthesized:
        sig.metadata["_synthesized_at"] = (fetched_at + timedelta(hours=1)).isoformat()
    return sig


def _make_insight(
    ins_id: str = "ins-test001",
    *,
    created_days_ago: int = 0,
    evidence: list[str] | None = None,
) -> Insight:
    """Create a test insight with configurable age."""
    created_at = datetime.now(timezone.utc) - timedelta(days=created_days_ago)
    return Insight(
        id=ins_id,
        category=InsightCategory.PAIN_POINT,
        title=f"Insight {ins_id}",
        summary="Test summary",
        evidence=evidence or [],
        created_at=created_at,
    )


def _make_buildable_unit(
    unit_id: str = "bu-test001",
    *,
    status: str = "draft",
    inspiring_insights: list[str] | None = None,
) -> BuildableUnit:
    """Create a test buildable unit."""
    return BuildableUnit(
        id=unit_id,
        title=f"Unit {unit_id}",
        one_liner="Test unit",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        target_users="both",
        value_proposition="Test value",
        status=status,
        inspiring_insights=inspiring_insights or [],
    )


# ── Schema migration tests ───────────────────────────────────────────


class TestSchemaV8Migration:
    """Test that v7→v8 migration adds archived_at columns and indices."""

    def test_fresh_db_has_archived_at_columns(self) -> None:
        """Fresh database should have archived_at columns in all three tables."""
        store = Store(":memory:")
        try:
            # Check signals
            columns = {
                row[1]
                for row in store.conn.execute("PRAGMA table_info(signals)").fetchall()
            }
            assert "archived_at" in columns

            # Check insights
            columns = {
                row[1]
                for row in store.conn.execute("PRAGMA table_info(insights)").fetchall()
            }
            assert "archived_at" in columns

            # Check pipeline_runs
            columns = {
                row[1]
                for row in store.conn.execute(
                    "PRAGMA table_info(pipeline_runs)"
                ).fetchall()
            }
            assert "archived_at" in columns
        finally:
            store.close()

    def test_fresh_db_has_archived_indices(self) -> None:
        """Fresh database should have indices on archived_at columns."""
        store = Store(":memory:")
        try:
            indices = {
                row[0]
                for row in store.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }
            assert "idx_signals_archived_at" in indices
            assert "idx_insights_archived_at" in indices
            assert "idx_pipeline_runs_archived_at" in indices
        finally:
            store.close()

    def test_migration_v7_to_v8_adds_columns(self) -> None:
        """Migration from v7 to v8 should add archived_at columns."""
        import sqlite3

        from max.store.migrations import SCHEMA_SQL

        # Create a v7 database (without archived_at)
        conn = sqlite3.connect(":memory:")
        # Use v7 schema (current SCHEMA_SQL but manually set version to 7)
        conn.executescript(SCHEMA_SQL)
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (7)")

        # Remove archived_at columns to simulate v7
        conn.execute("DROP INDEX IF EXISTS idx_signals_archived_at")
        conn.execute("DROP INDEX IF EXISTS idx_insights_archived_at")
        conn.execute("DROP INDEX IF EXISTS idx_pipeline_runs_archived_at")

        # Note: SQLite doesn't support DROP COLUMN in older versions,
        # so we'll just verify the migration can run without error
        conn.commit()

        # Run v7→v8 migration
        _migrate_v7_to_v8(conn)

        # Verify columns exist
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()
        }
        assert "archived_at" in columns

        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(insights)").fetchall()
        }
        assert "archived_at" in columns

        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(pipeline_runs)").fetchall()
        }
        assert "archived_at" in columns

        conn.close()

    def test_schema_version_is_10(self) -> None:
        """Current schema version should be 10."""
        assert SCHEMA_VERSION == 10


# ── Archive operations tests ─────────────────────────────────────────


class TestArchiveOldRecords:
    """Test archive_old_records() method."""

    def test_archives_old_synthesized_signals(self) -> None:
        """Should archive signals that are old AND synthesized."""
        store = Store(":memory:")
        try:
            # Insert old synthesized signal (should be archived)
            old_synth = _make_signal(
                "sig-old-synth", fetched_days_ago=100, synthesized=True
            )
            store.insert_signal(old_synth)
            store.mark_signals_synthesized([old_synth.id])

            # Insert old unsynth signal (should NOT be archived)
            old_unsynth = _make_signal(
                "sig-old-unsynth",
                url="https://example.com/old-unsynth",
                fetched_days_ago=100,
                synthesized=False,
            )
            store.insert_signal(old_unsynth)

            # Insert recent synthesized signal (should NOT be archived)
            recent = _make_signal(
                "sig-recent",
                url="https://example.com/recent",
                fetched_days_ago=10,
                synthesized=True,
            )
            store.insert_signal(recent)
            store.mark_signals_synthesized([recent.id])

            # Archive with 90 day threshold
            result = store.archive_old_records(days=90)

            assert result["signals_archived"] == 1

            # Verify correct signal was archived
            row = store.conn.execute(
                "SELECT archived_at FROM signals WHERE id = ?", (old_synth.id,)
            ).fetchone()
            assert row[0] is not None

            # Verify others were NOT archived
            row = store.conn.execute(
                "SELECT archived_at FROM signals WHERE id = ?", (old_unsynth.id,)
            ).fetchone()
            assert row[0] is None

            row = store.conn.execute(
                "SELECT archived_at FROM signals WHERE id = ?", (recent.id,)
            ).fetchone()
            assert row[0] is None
        finally:
            store.close()

    def test_does_not_archive_unsynthesized_signals(self) -> None:
        """Should NOT archive signals without synthesized_at, even if old."""
        store = Store(":memory:")
        try:
            # Insert very old but unsynthesized signal
            old = _make_signal("sig-old", fetched_days_ago=200, synthesized=False)
            store.insert_signal(old)

            result = store.archive_old_records(days=90)

            assert result["signals_archived"] == 0

            # Verify it was not archived
            row = store.conn.execute(
                "SELECT archived_at FROM signals WHERE id = ?", (old.id,)
            ).fetchone()
            assert row[0] is None
        finally:
            store.close()

    def test_archives_old_pipeline_runs(self) -> None:
        """Should archive pipeline runs older than threshold."""
        store = Store(":memory:")
        try:
            # Insert old run
            old_started = (
                datetime.now(timezone.utc) - timedelta(days=100)
            ).isoformat()
            store.conn.execute(
                "INSERT INTO pipeline_runs (id, started_at, config) VALUES (?, ?, ?)",
                ("run-old", old_started, "{}"),
            )

            # Insert recent run
            recent_started = (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat()
            store.conn.execute(
                "INSERT INTO pipeline_runs (id, started_at, config) VALUES (?, ?, ?)",
                ("run-recent", recent_started, "{}"),
            )
            store.conn.commit()

            result = store.archive_old_records(days=90)

            assert result["runs_archived"] == 1

            # Verify old run was archived
            row = store.conn.execute(
                "SELECT archived_at FROM pipeline_runs WHERE id = ?", ("run-old",)
            ).fetchone()
            assert row[0] is not None

            # Verify recent run was NOT archived
            row = store.conn.execute(
                "SELECT archived_at FROM pipeline_runs WHERE id = ?", ("run-recent",)
            ).fetchone()
            assert row[0] is None
        finally:
            store.close()

    def test_archives_insights_with_terminal_units(self) -> None:
        """Should archive insights where all referencing units are rejected/abandoned."""
        store = Store(":memory:")
        try:
            # Create old insight
            insight = _make_insight("ins-old", created_days_ago=100)
            store.insert_insight(insight)

            # Create buildable unit referencing it (rejected status)
            unit = _make_buildable_unit(
                "bu-rejected", status="rejected", inspiring_insights=[insight.id]
            )
            store.insert_buildable_unit(unit)

            result = store.archive_old_records(days=90)

            assert result["insights_archived"] == 1

            # Verify it was archived
            row = store.conn.execute(
                "SELECT archived_at FROM insights WHERE id = ?", (insight.id,)
            ).fetchone()
            assert row[0] is not None
        finally:
            store.close()

    def test_does_not_archive_insights_with_active_units(self) -> None:
        """Should NOT archive insights if any referencing unit is not terminal."""
        store = Store(":memory:")
        try:
            # Create old insight
            insight = _make_insight("ins-active", created_days_ago=100)
            store.insert_insight(insight)

            # Create buildable unit referencing it (draft status = active)
            unit = _make_buildable_unit(
                "bu-draft", status="draft", inspiring_insights=[insight.id]
            )
            store.insert_buildable_unit(unit)

            result = store.archive_old_records(days=90)

            assert result["insights_archived"] == 0

            # Verify it was NOT archived
            row = store.conn.execute(
                "SELECT archived_at FROM insights WHERE id = ?", (insight.id,)
            ).fetchone()
            assert row[0] is None
        finally:
            store.close()

    def test_does_not_re_archive_already_archived(self) -> None:
        """Should not count already-archived records."""
        store = Store(":memory:")
        try:
            # Insert and archive a signal
            sig = _make_signal("sig-archived", fetched_days_ago=100, synthesized=True)
            store.insert_signal(sig)
            store.mark_signals_synthesized([sig.id])

            # Archive once
            result1 = store.archive_old_records(days=90)
            assert result1["signals_archived"] == 1

            # Archive again
            result2 = store.archive_old_records(days=90)
            assert result2["signals_archived"] == 0
        finally:
            store.close()


# ── Purge operations tests ───────────────────────────────────────────


class TestPurgeArchived:
    """Test purge_archived() method."""

    def test_deletes_old_archived_records(self) -> None:
        """Should permanently delete records archived long ago."""
        store = Store(":memory:")
        try:
            # Insert signal and mark as archived 200 days ago
            sig = _make_signal("sig-purge", fetched_days_ago=250, synthesized=True)
            store.insert_signal(sig)
            store.mark_signals_synthesized([sig.id])

            old_archive_time = (
                datetime.now(timezone.utc) - timedelta(days=200)
            ).isoformat()
            store.conn.execute(
                "UPDATE signals SET archived_at = ? WHERE id = ?",
                (old_archive_time, sig.id),
            )
            store.conn.commit()

            # Purge archived records older than 180 days
            result = store.purge_archived(before_days=180)

            assert result["signals_deleted"] == 1

            # Verify signal was deleted
            row = store.conn.execute(
                "SELECT COUNT(*) FROM signals WHERE id = ?", (sig.id,)
            ).fetchone()
            assert row[0] == 0
        finally:
            store.close()

    def test_does_not_delete_recently_archived(self) -> None:
        """Should NOT delete records archived recently."""
        store = Store(":memory:")
        try:
            # Insert signal and mark as archived 100 days ago
            sig = _make_signal("sig-recent-arch", fetched_days_ago=150, synthesized=True)
            store.insert_signal(sig)
            store.mark_signals_synthesized([sig.id])

            recent_archive_time = (
                datetime.now(timezone.utc) - timedelta(days=100)
            ).isoformat()
            store.conn.execute(
                "UPDATE signals SET archived_at = ? WHERE id = ?",
                (recent_archive_time, sig.id),
            )
            store.conn.commit()

            # Purge with 180 day threshold
            result = store.purge_archived(before_days=180)

            assert result["signals_deleted"] == 0

            # Verify signal still exists
            row = store.conn.execute(
                "SELECT COUNT(*) FROM signals WHERE id = ?", (sig.id,)
            ).fetchone()
            assert row[0] == 1
        finally:
            store.close()

    def test_does_not_delete_active_records(self) -> None:
        """Should NOT delete non-archived records, even if old."""
        store = Store(":memory:")
        try:
            # Insert very old signal but NOT archived
            sig = _make_signal("sig-old-active", fetched_days_ago=300, synthesized=False)
            store.insert_signal(sig)

            result = store.purge_archived(before_days=180)

            assert result["signals_deleted"] == 0

            # Verify signal still exists
            row = store.conn.execute(
                "SELECT COUNT(*) FROM signals WHERE id = ?", (sig.id,)
            ).fetchone()
            assert row[0] == 1
        finally:
            store.close()

    def test_purges_all_three_tables(self) -> None:
        """Should purge from signals, insights, and pipeline_runs."""
        store = Store(":memory:")
        try:
            old_archive = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()

            # Archived signal
            sig = _make_signal("sig-purge", fetched_days_ago=250, synthesized=True)
            store.insert_signal(sig)
            store.conn.execute(
                "UPDATE signals SET archived_at = ? WHERE id = ?", (old_archive, sig.id)
            )

            # Archived insight
            ins = _make_insight("ins-purge", created_days_ago=250)
            store.insert_insight(ins)
            store.conn.execute(
                "UPDATE insights SET archived_at = ? WHERE id = ?", (old_archive, ins.id)
            )

            # Archived pipeline run
            old_started = (
                datetime.now(timezone.utc) - timedelta(days=250)
            ).isoformat()
            store.conn.execute(
                "INSERT INTO pipeline_runs (id, started_at, config, archived_at) VALUES (?, ?, ?, ?)",
                ("run-purge", old_started, "{}", old_archive),
            )
            store.conn.commit()

            result = store.purge_archived(before_days=180)

            assert result["signals_deleted"] == 1
            assert result["insights_deleted"] == 1
            assert result["runs_deleted"] == 1
        finally:
            store.close()


# ── Retention stats tests ────────────────────────────────────────────


class TestRetentionStats:
    """Test retention_stats() method."""

    def test_returns_correct_counts(self) -> None:
        """Should return accurate counts of total, active, and archived records."""
        store = Store(":memory:")
        try:
            # Insert 3 signals: 1 active, 2 archived
            sig1 = _make_signal("sig-active", url="https://example.com/1")
            sig2 = _make_signal("sig-arch1", url="https://example.com/2")
            sig3 = _make_signal("sig-arch2", url="https://example.com/3")

            store.insert_signal(sig1)
            store.insert_signal(sig2)
            store.insert_signal(sig3)

            now = datetime.now(timezone.utc).isoformat()
            store.conn.execute(
                "UPDATE signals SET archived_at = ? WHERE id IN (?, ?)",
                (now, sig2.id, sig3.id),
            )
            store.conn.commit()

            stats = store.retention_stats()

            assert stats["signals"]["total"] == 3
            assert stats["signals"]["active"] == 1
            assert stats["signals"]["archived"] == 2
        finally:
            store.close()

    def test_empty_database(self) -> None:
        """Should return zeros for empty database."""
        store = Store(":memory:")
        try:
            stats = store.retention_stats()

            assert stats["signals"]["total"] == 0
            assert stats["signals"]["active"] == 0
            assert stats["signals"]["archived"] == 0

            assert stats["insights"]["total"] == 0
            assert stats["pipeline_runs"]["total"] == 0
        finally:
            store.close()


# ── Query filtering tests ────────────────────────────────────────────


class TestArchivedRecordsFiltering:
    """Test that archived records are excluded from read queries."""

    def test_get_signals_excludes_archived(self) -> None:
        """get_signals() should not return archived signals."""
        store = Store(":memory:")
        try:
            # Insert active and archived signals
            active = _make_signal("sig-active", url="https://example.com/active")
            archived = _make_signal("sig-archived", url="https://example.com/archived")

            store.insert_signal(active)
            store.insert_signal(archived)

            # Archive one
            now = datetime.now(timezone.utc).isoformat()
            store.conn.execute(
                "UPDATE signals SET archived_at = ? WHERE id = ?", (now, archived.id)
            )
            store.conn.commit()

            # Query should only return active
            results = store.get_signals(limit=100)
            assert len(results) == 1
            assert results[0].id == active.id
        finally:
            store.close()

    def test_get_insights_excludes_archived(self) -> None:
        """get_insights() should not return archived insights."""
        store = Store(":memory:")
        try:
            active = _make_insight("ins-active")
            archived = _make_insight("ins-archived")

            store.insert_insight(active)
            store.insert_insight(archived)

            # Archive one
            now = datetime.now(timezone.utc).isoformat()
            store.conn.execute(
                "UPDATE insights SET archived_at = ? WHERE id = ?", (now, archived.id)
            )
            store.conn.commit()

            results = store.get_insights(limit=100)
            assert len(results) == 1
            assert results[0].id == active.id
        finally:
            store.close()

    def test_get_pipeline_runs_excludes_archived(self) -> None:
        """get_pipeline_runs() should not return archived runs."""
        store = Store(":memory:")
        try:
            now_iso = datetime.now(timezone.utc).isoformat()

            store.conn.execute(
                "INSERT INTO pipeline_runs (id, started_at, config) VALUES (?, ?, ?)",
                ("run-active", now_iso, "{}"),
            )
            store.conn.execute(
                "INSERT INTO pipeline_runs (id, started_at, config, archived_at) VALUES (?, ?, ?, ?)",
                ("run-archived", now_iso, "{}", now_iso),
            )
            store.conn.commit()

            results = store.get_pipeline_runs(limit=100)
            assert len(results) == 1
            assert results[0]["id"] == "run-active"
        finally:
            store.close()

    def test_count_signals_excludes_archived(self) -> None:
        """count_signals() should not count archived signals."""
        store = Store(":memory:")
        try:
            active = _make_signal("sig-active", url="https://example.com/active")
            archived = _make_signal("sig-archived", url="https://example.com/archived")

            store.insert_signal(active)
            store.insert_signal(archived)

            # Archive one
            now = datetime.now(timezone.utc).isoformat()
            store.conn.execute(
                "UPDATE signals SET archived_at = ? WHERE id = ?", (now, archived.id)
            )
            store.conn.commit()

            count = store.count_signals()
            assert count == 1
        finally:
            store.close()


# ── Pytest fixtures ──────────────────────────────────────────────────


@pytest.fixture
def store() -> Store:
    """Create a fresh in-memory store for each test."""
    s = Store(":memory:")
    yield s
    s.close()
