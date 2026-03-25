"""SQLite schema creation and migrations."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    embedding TEXT NOT NULL,
    PRIMARY KEY (id, entity_type)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist, apply migrations if needed."""
    conn.executescript(SCHEMA_SQL)

    cursor = conn.execute("SELECT COUNT(*) FROM schema_version")
    if cursor.fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
