"""Tests for database migration system in src/max/store/migrations.py."""

from __future__ import annotations

import sqlite3

import pytest

from max.store.migrations import (
    SCHEMA_SQL,
    SCHEMA_VERSION,
    _migrate_v1_to_v2,
    _migrate_v2_to_v3,
    _migrate_v3_to_v4,
    _migrate_v4_to_v5,
    _migrate_v5_to_v6,
    ensure_schema,
)
from max.store.db import Store


EXPECTED_TABLES = {
    "signals",
    "insights",
    "buildable_units",
    "evaluations",
    "tact_specs",
    "feedback",
    "pipeline_runs",
    "embeddings",
    "pipeline_run_domains",
}


def _get_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
        " AND name NOT IN ('schema_version', 'sqlite_sequence')"
    ).fetchall()
    return {row[0] for row in rows}


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _get_indices(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _get_schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT version FROM schema_version").fetchone()[0]


# V1 schema: signals, insights, buildable_units (no domain), evaluations,
# tact_specs, feedback (no pipeline_run_id). No synthesized_at, no signal_role,
# no pipeline_runs table, no embeddings table, no adapter_metrics column.
V1_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
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
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_url ON signals(url);

CREATE TABLE IF NOT EXISTS insights (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.5,
    domains TEXT NOT NULL DEFAULT '[]',
    implications TEXT NOT NULL DEFAULT '[]',
    time_horizon TEXT NOT NULL DEFAULT 'near_term',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS buildable_units (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    one_liner TEXT NOT NULL,
    category TEXT NOT NULL,
    ideation_mode TEXT NOT NULL DEFAULT 'direct',
    problem TEXT NOT NULL,
    solution TEXT NOT NULL,
    target_users TEXT NOT NULL DEFAULT 'both',
    value_proposition TEXT NOT NULL,
    inspiring_insights TEXT NOT NULL DEFAULT '[]',
    evidence_signals TEXT NOT NULL DEFAULT '[]',
    tech_approach TEXT NOT NULL DEFAULT '',
    suggested_stack TEXT NOT NULL DEFAULT '{}',
    composability_notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluations (
    buildable_unit_id TEXT PRIMARY KEY,
    pain_severity TEXT NOT NULL,
    addressable_scale TEXT NOT NULL,
    build_effort TEXT NOT NULL,
    composability TEXT NOT NULL,
    competitive_density TEXT NOT NULL,
    timing_fit TEXT NOT NULL,
    compounding_value TEXT NOT NULL,
    overall_score REAL NOT NULL DEFAULT 0.0,
    rank INTEGER,
    strengths TEXT NOT NULL DEFAULT '[]',
    weaknesses TEXT NOT NULL DEFAULT '[]',
    recommendation TEXT NOT NULL DEFAULT 'maybe',
    weights_used TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
);

CREATE TABLE IF NOT EXISTS tact_specs (
    buildable_unit_id TEXT PRIMARY KEY,
    spec_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buildable_unit_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    dimension_values TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
);
"""


def _create_v1_db() -> sqlite3.Connection:
    """Create an in-memory database with v1 schema."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(V1_SCHEMA_SQL)
    conn.execute("INSERT INTO schema_version (version) VALUES (1)")
    conn.commit()
    return conn


# ── 1. Fresh database gets schema v6 with all 8 tables ──────────────


class TestFreshSchema:
    def test_fresh_db_creates_all_tables(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        assert _get_tables(conn) == EXPECTED_TABLES
        conn.close()

    def test_fresh_db_sets_schema_version(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        assert _get_schema_version(conn) == SCHEMA_VERSION
        conn.close()

    def test_fresh_db_via_store(self) -> None:
        s = Store(":memory:")
        assert _get_tables(s.conn) == EXPECTED_TABLES
        assert _get_schema_version(s.conn) == SCHEMA_VERSION
        s.close()

    def test_fresh_db_signals_has_all_columns(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        cols = _get_columns(conn, "signals")
        assert "synthesized_at" in cols
        assert "signal_role" in cols
        conn.close()

    def test_fresh_db_buildable_units_has_domain(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        assert "domain" in _get_columns(conn, "buildable_units")
        conn.close()

    def test_fresh_db_feedback_has_pipeline_run_id(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        assert "pipeline_run_id" in _get_columns(conn, "feedback")
        conn.close()

    def test_fresh_db_pipeline_runs_has_adapter_metrics(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        assert "adapter_metrics" in _get_columns(conn, "pipeline_runs")
        conn.close()

    def test_fresh_db_embeddings_columns(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        cols = _get_columns(conn, "embeddings")
        assert cols == {"id", "entity_type", "embedding"}
        conn.close()


# ── 2. Incremental migrations apply cleanly ──────────────────────────


class TestIncrementalMigrations:
    def test_migrate_v1_to_v2_adds_synthesized_at(self) -> None:
        conn = _create_v1_db()
        assert "synthesized_at" not in _get_columns(conn, "signals")
        _migrate_v1_to_v2(conn)
        assert "synthesized_at" in _get_columns(conn, "signals")
        conn.close()

    def test_migrate_v2_to_v3_adds_signal_role(self) -> None:
        conn = _create_v1_db()
        _migrate_v1_to_v2(conn)
        assert "signal_role" not in _get_columns(conn, "signals")
        _migrate_v2_to_v3(conn)
        assert "signal_role" in _get_columns(conn, "signals")
        conn.close()

    def test_migrate_v3_to_v4_adds_pipeline_runs_and_feedback_column(self) -> None:
        conn = _create_v1_db()
        _migrate_v1_to_v2(conn)
        _migrate_v2_to_v3(conn)
        assert "pipeline_runs" not in _get_tables(conn)
        assert "pipeline_run_id" not in _get_columns(conn, "feedback")
        _migrate_v3_to_v4(conn)
        assert "pipeline_runs" in _get_tables(conn)
        assert "pipeline_run_id" in _get_columns(conn, "feedback")
        conn.close()

    def test_migrate_v3_to_v4_pipeline_runs_columns(self) -> None:
        conn = _create_v1_db()
        _migrate_v1_to_v2(conn)
        _migrate_v2_to_v3(conn)
        _migrate_v3_to_v4(conn)
        cols = _get_columns(conn, "pipeline_runs")
        expected = {
            "id", "started_at", "completed_at", "config",
            "signals_fetched", "signals_new", "insights_generated",
            "ideas_generated", "ideas_evaluated", "specs_generated",
            "clusters_found", "gaps_detected", "avg_idea_score",
            "fetch_allocation", "token_usage",
        }
        assert expected.issubset(cols)
        conn.close()

    def test_migrate_v4_to_v5_adds_adapter_metrics(self) -> None:
        conn = _create_v1_db()
        _migrate_v1_to_v2(conn)
        _migrate_v2_to_v3(conn)
        _migrate_v3_to_v4(conn)
        assert "adapter_metrics" not in _get_columns(conn, "pipeline_runs")
        _migrate_v4_to_v5(conn)
        assert "adapter_metrics" in _get_columns(conn, "pipeline_runs")
        conn.close()

    def test_migrate_v5_to_v6_adds_domain(self) -> None:
        conn = _create_v1_db()
        _migrate_v1_to_v2(conn)
        _migrate_v2_to_v3(conn)
        _migrate_v3_to_v4(conn)
        _migrate_v4_to_v5(conn)
        assert "domain" not in _get_columns(conn, "buildable_units")
        _migrate_v5_to_v6(conn)
        assert "domain" in _get_columns(conn, "buildable_units")
        conn.close()


# ── 3. Full migration path: v1 → v6 via ensure_schema ───────────────


class TestFullMigrationPath:
    def test_v1_to_v6_via_ensure_schema(self) -> None:
        conn = _create_v1_db()
        assert _get_schema_version(conn) == 1
        ensure_schema(conn)
        assert _get_schema_version(conn) == SCHEMA_VERSION

        # v2 addition
        assert "synthesized_at" in _get_columns(conn, "signals")
        # v3 addition
        assert "signal_role" in _get_columns(conn, "signals")
        # v4 additions
        assert "pipeline_runs" in _get_tables(conn)
        assert "pipeline_run_id" in _get_columns(conn, "feedback")
        # v5 addition
        assert "adapter_metrics" in _get_columns(conn, "pipeline_runs")
        # v6 addition
        assert "domain" in _get_columns(conn, "buildable_units")
        # v6 also creates embeddings table via SCHEMA_SQL executescript
        assert "embeddings" in _get_tables(conn)
        conn.close()

    def test_v1_data_survives_migration(self) -> None:
        conn = _create_v1_db()
        conn.execute(
            """INSERT INTO signals (id, source_type, source_adapter, title,
               content, url, fetched_at)
               VALUES ('sig-1', 'forum', 'hn', 'Test', 'content',
                       'https://example.com/1', '2025-01-01T00:00:00')"""
        )
        conn.execute(
            """INSERT INTO buildable_units (id, title, one_liner, category,
               problem, solution, value_proposition, status, created_at, updated_at)
               VALUES ('bu-1', 'Unit', 'liner', 'cli_tool', 'p', 's', 'v',
                       'draft', '2025-01-01', '2025-01-01')"""
        )
        conn.commit()

        ensure_schema(conn)

        # Data still intact
        row = conn.execute("SELECT * FROM signals WHERE id = 'sig-1'").fetchone()
        assert row is not None
        row = conn.execute("SELECT * FROM buildable_units WHERE id = 'bu-1'").fetchone()
        assert row is not None
        conn.close()

    def test_v1_signal_gets_default_values_after_migration(self) -> None:
        conn = _create_v1_db()
        conn.execute(
            """INSERT INTO signals (id, source_type, source_adapter, title,
               content, url, fetched_at)
               VALUES ('sig-def', 'forum', 'hn', 'Test', 'content',
                       'https://example.com/def', '2025-01-01T00:00:00')"""
        )
        conn.commit()

        ensure_schema(conn)

        row = conn.execute("SELECT synthesized_at, signal_role FROM signals WHERE id = 'sig-def'").fetchone()
        assert row[0] is None  # synthesized_at default
        assert row[1] == ""    # signal_role default
        conn.close()


# ── 4. Idempotency ──────────────────────────────────────────────────


class TestIdempotency:
    def test_ensure_schema_twice_on_fresh_db(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        ensure_schema(conn)
        assert _get_schema_version(conn) == SCHEMA_VERSION
        assert _get_tables(conn) == EXPECTED_TABLES
        conn.close()

    def test_ensure_schema_twice_on_migrated_db(self) -> None:
        conn = _create_v1_db()
        ensure_schema(conn)
        ensure_schema(conn)
        assert _get_schema_version(conn) == SCHEMA_VERSION
        conn.close()

    def test_ensure_schema_preserves_data_on_second_call(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        conn.execute(
            """INSERT INTO signals (id, source_type, source_adapter, title,
               content, url, fetched_at, signal_role)
               VALUES ('sig-idem', 'forum', 'hn', 'Test', 'content',
                       'https://example.com/idem', '2025-01-01T00:00:00', '')"""
        )
        conn.commit()

        ensure_schema(conn)

        assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 1
        conn.close()

    def test_store_idempotent_reopen(self, tmp_path) -> None:
        db_path = str(tmp_path / "idem.db")
        s1 = Store(db_path=db_path)
        s1.close()
        s2 = Store(db_path=db_path)
        assert _get_schema_version(s2.conn) == SCHEMA_VERSION
        s2.close()

    def test_individual_migrations_idempotent(self) -> None:
        conn = _create_v1_db()
        _migrate_v1_to_v2(conn)
        _migrate_v1_to_v2(conn)  # safe to call again
        assert "synthesized_at" in _get_columns(conn, "signals")

        _migrate_v2_to_v3(conn)
        _migrate_v2_to_v3(conn)
        assert "signal_role" in _get_columns(conn, "signals")

        _migrate_v3_to_v4(conn)
        _migrate_v3_to_v4(conn)
        assert "pipeline_runs" in _get_tables(conn)

        _migrate_v4_to_v5(conn)
        _migrate_v4_to_v5(conn)
        assert "adapter_metrics" in _get_columns(conn, "pipeline_runs")

        _migrate_v5_to_v6(conn)
        _migrate_v5_to_v6(conn)
        assert "domain" in _get_columns(conn, "buildable_units")
        conn.close()


# ── 5. Schema version pragma ────────────────────────────────────────


class TestSchemaVersion:
    def test_fresh_db_version(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        assert _get_schema_version(conn) == 7
        conn.close()

    def test_v1_migrated_to_current(self) -> None:
        conn = _create_v1_db()
        assert _get_schema_version(conn) == 1
        ensure_schema(conn)
        assert _get_schema_version(conn) == SCHEMA_VERSION
        conn.close()

    def test_already_current_version_not_changed(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        assert _get_schema_version(conn) == SCHEMA_VERSION
        # Call again — version row count stays at 1
        ensure_schema(conn)
        count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        assert count == 1
        assert _get_schema_version(conn) == SCHEMA_VERSION
        conn.close()

    def test_intermediate_version_triggers_remaining_migrations(self) -> None:
        """A db at v3 should only run v4, v5, v6 migrations."""
        conn = _create_v1_db()
        # Manually advance to v3
        _migrate_v1_to_v2(conn)
        _migrate_v2_to_v3(conn)
        conn.execute("UPDATE schema_version SET version = 3")
        conn.commit()

        # Verify pre-conditions: no pipeline_runs, no domain, no adapter_metrics
        assert "pipeline_runs" not in _get_tables(conn)
        assert "domain" not in _get_columns(conn, "buildable_units")

        ensure_schema(conn)

        assert _get_schema_version(conn) == SCHEMA_VERSION
        # v4+ additions present
        assert "pipeline_runs" in _get_tables(conn)
        assert "pipeline_run_id" in _get_columns(conn, "feedback")
        assert "adapter_metrics" in _get_columns(conn, "pipeline_runs")
        assert "domain" in _get_columns(conn, "buildable_units")
        conn.close()


# ── 6. Indices ──────────────────────────────────────────────────────


class TestIndices:
    def test_idx_signals_url_created(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        indices = _get_indices(conn)
        assert "idx_signals_url" in indices
        conn.close()

    def test_idx_signals_url_is_unique(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        conn.execute(
            """INSERT INTO signals (id, source_type, source_adapter, title,
               content, url, fetched_at, signal_role)
               VALUES ('sig-u1', 'forum', 'hn', 'T1', 'c1',
                       'https://example.com/unique', '2025-01-01', '')"""
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO signals (id, source_type, source_adapter, title,
                   content, url, fetched_at, signal_role)
                   VALUES ('sig-u2', 'forum', 'hn', 'T2', 'c2',
                           'https://example.com/unique', '2025-01-01', '')"""
            )
        conn.close()

    def test_index_survives_migration(self) -> None:
        conn = _create_v1_db()
        ensure_schema(conn)
        assert "idx_signals_url" in _get_indices(conn)
        conn.close()
