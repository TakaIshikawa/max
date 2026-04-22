"""SQLite schema creation and migrations."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 19

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
    metadata TEXT NOT NULL DEFAULT '{}',
    synthesized_at TEXT DEFAULT NULL,
    signal_role TEXT NOT NULL DEFAULT '',
    archived_at TEXT DEFAULT NULL
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
    created_at TEXT NOT NULL,
    archived_at TEXT DEFAULT NULL
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
    specific_user TEXT NOT NULL DEFAULT '',
    buyer TEXT NOT NULL DEFAULT '',
    workflow_context TEXT NOT NULL DEFAULT '',
    current_workaround TEXT NOT NULL DEFAULT '',
    why_now TEXT NOT NULL DEFAULT '',
    validation_plan TEXT NOT NULL DEFAULT '',
    first_10_customers TEXT NOT NULL DEFAULT '',
    domain_risks TEXT NOT NULL DEFAULT '[]',
    evidence_rationale TEXT NOT NULL DEFAULT '',
    novelty_score REAL NOT NULL DEFAULT 0.0,
    usefulness_score REAL NOT NULL DEFAULT 0.0,
    quality_score REAL NOT NULL DEFAULT 0.0,
    rejection_tags TEXT NOT NULL DEFAULT '[]',
    inspiring_insights TEXT NOT NULL DEFAULT '[]',
    evidence_signals TEXT NOT NULL DEFAULT '[]',
    tech_approach TEXT NOT NULL DEFAULT '',
    suggested_stack TEXT NOT NULL DEFAULT '{}',
    composability_notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    domain TEXT NOT NULL DEFAULT '',
    prior_art_status TEXT NOT NULL DEFAULT 'unchecked',
    source_idea_ids TEXT NOT NULL DEFAULT '[]',
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

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buildable_unit_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    dimension_values TEXT NOT NULL DEFAULT '{}',
    approval_score INTEGER DEFAULT NULL,
    created_at TEXT NOT NULL,
    pipeline_run_id TEXT DEFAULT NULL,
    FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    config TEXT NOT NULL DEFAULT '{}',
    signals_fetched INTEGER NOT NULL DEFAULT 0,
    signals_new INTEGER NOT NULL DEFAULT 0,
    insights_generated INTEGER NOT NULL DEFAULT 0,
    ideas_generated INTEGER NOT NULL DEFAULT 0,
    ideas_evaluated INTEGER NOT NULL DEFAULT 0,
    clusters_found INTEGER NOT NULL DEFAULT 0,
    gaps_detected INTEGER NOT NULL DEFAULT 0,
    avg_idea_score REAL NOT NULL DEFAULT 0.0,
    fetch_allocation TEXT NOT NULL DEFAULT '{}',
    token_usage TEXT NOT NULL DEFAULT '{}',
    adapter_metrics TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'running',
    error_message TEXT NOT NULL DEFAULT '',
    archived_at TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_run_domains (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pipeline_runs(id),
    domain TEXT NOT NULL,
    signals_fetched INTEGER DEFAULT 0,
    insights_generated INTEGER DEFAULT 0,
    ideas_generated INTEGER DEFAULT 0,
    ideas_evaluated INTEGER DEFAULT 0,
    avg_score REAL DEFAULT 0.0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prd_run_id ON pipeline_run_domains(run_id);
CREATE INDEX IF NOT EXISTS idx_prd_domain ON pipeline_run_domains(domain);

CREATE TABLE IF NOT EXISTS prior_art_matches (
    id TEXT PRIMARY KEY,
    buildable_unit_id TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    relevance_score REAL NOT NULL DEFAULT 0.0,
    match_signals TEXT NOT NULL DEFAULT '{}',
    search_query TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
);

CREATE INDEX IF NOT EXISTS idx_prior_art_bu_id ON prior_art_matches(buildable_unit_id);

CREATE TABLE IF NOT EXISTS idea_critiques (
    id TEXT PRIMARY KEY,
    buildable_unit_id TEXT NOT NULL,
    pipeline_run_id TEXT DEFAULT NULL,
    stage TEXT NOT NULL DEFAULT 'ideation_critique',
    dimensions TEXT NOT NULL DEFAULT '{}',
    reasoning TEXT NOT NULL DEFAULT '',
    rejection_tags TEXT NOT NULL DEFAULT '[]',
    evidence_pack TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
);

CREATE INDEX IF NOT EXISTS idx_idea_critiques_bu_id ON idea_critiques(buildable_unit_id);

CREATE TABLE IF NOT EXISTS idea_memory (
    id TEXT PRIMARY KEY,
    buildable_unit_id TEXT DEFAULT NULL,
    domain TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL,
    pattern TEXT NOT NULL,
    rejection_tags TEXT NOT NULL DEFAULT '[]',
    score REAL NOT NULL DEFAULT 0.0,
    evidence_rationale TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
);

CREATE INDEX IF NOT EXISTS idx_idea_memory_domain ON idea_memory(domain);
CREATE INDEX IF NOT EXISTS idx_idea_memory_outcome ON idea_memory(outcome);

CREATE TABLE IF NOT EXISTS design_briefs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    theme TEXT NOT NULL DEFAULT '',
    readiness_score REAL NOT NULL DEFAULT 0.0,
    lead_idea_id TEXT NOT NULL,
    buyer TEXT NOT NULL DEFAULT '',
    specific_user TEXT NOT NULL DEFAULT '',
    workflow_context TEXT NOT NULL DEFAULT '',
    why_this_now TEXT NOT NULL DEFAULT '',
    merged_product_concept TEXT NOT NULL DEFAULT '',
    synthesis_rationale TEXT NOT NULL DEFAULT '',
    mvp_scope TEXT NOT NULL DEFAULT '[]',
    first_milestones TEXT NOT NULL DEFAULT '[]',
    validation_plan TEXT NOT NULL DEFAULT '',
    risks TEXT NOT NULL DEFAULT '[]',
    source_idea_ids TEXT NOT NULL DEFAULT '[]',
    design_status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (lead_idea_id) REFERENCES buildable_units(id)
);

CREATE TABLE IF NOT EXISTS design_brief_sources (
    brief_id TEXT NOT NULL,
    idea_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'source',
    rank INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (brief_id, idea_id, role),
    FOREIGN KEY (brief_id) REFERENCES design_briefs(id),
    FOREIGN KEY (idea_id) REFERENCES buildable_units(id)
);

CREATE INDEX IF NOT EXISTS idx_design_briefs_domain ON design_briefs(domain);
CREATE INDEX IF NOT EXISTS idx_design_briefs_status ON design_briefs(design_status);
CREATE INDEX IF NOT EXISTS idx_design_brief_sources_idea ON design_brief_sources(idea_id);

CREATE TABLE IF NOT EXISTS domain_quality_scores (
    id TEXT PRIMARY KEY,
    buildable_unit_id TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    profile_name TEXT NOT NULL DEFAULT '',
    rubric_version TEXT NOT NULL DEFAULT 'v1',
    dimensions TEXT NOT NULL DEFAULT '{}',
    overall_score REAL NOT NULL DEFAULT 0.0,
    passed_gate INTEGER NOT NULL DEFAULT 0,
    rejection_tags TEXT NOT NULL DEFAULT '[]',
    reasoning TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
);

CREATE TABLE IF NOT EXISTS domain_quality_memory (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL,
    pattern TEXT NOT NULL,
    source_idea_id TEXT DEFAULT NULL,
    source_design_brief_id TEXT DEFAULT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    score REAL NOT NULL DEFAULT 0.0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_idea_id) REFERENCES buildable_units(id),
    FOREIGN KEY (source_design_brief_id) REFERENCES design_briefs(id)
);

CREATE INDEX IF NOT EXISTS idx_domain_quality_scores_unit ON domain_quality_scores(buildable_unit_id);
CREATE INDEX IF NOT EXISTS idx_domain_quality_scores_domain ON domain_quality_scores(domain);
CREATE INDEX IF NOT EXISTS idx_domain_quality_memory_domain ON domain_quality_memory(domain);
CREATE INDEX IF NOT EXISTS idx_domain_quality_memory_outcome ON domain_quality_memory(outcome);

CREATE TABLE IF NOT EXISTS domain_quality_eval_runs (
    id TEXT PRIMARY KEY,
    profile_name TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL DEFAULT '',
    rubric_version TEXT NOT NULL DEFAULT 'v1',
    baseline_pipeline_run_id TEXT NOT NULL DEFAULT '',
    rubric_pipeline_run_id TEXT NOT NULL DEFAULT '',
    baseline_ideas INTEGER NOT NULL DEFAULT 0,
    rubric_ideas INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS domain_quality_eval_items (
    id TEXT PRIMARY KEY,
    eval_run_id TEXT NOT NULL,
    buildable_unit_id TEXT NOT NULL,
    cohort TEXT NOT NULL,
    domain_quality_score REAL DEFAULT NULL,
    passed_gate INTEGER DEFAULT NULL,
    evaluation_score REAL DEFAULT NULL,
    review_outcome TEXT DEFAULT NULL,
    approval_score INTEGER DEFAULT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (eval_run_id) REFERENCES domain_quality_eval_runs(id),
    FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
);

CREATE INDEX IF NOT EXISTS idx_domain_quality_eval_items_run ON domain_quality_eval_items(eval_run_id);
CREATE INDEX IF NOT EXISTS idx_domain_quality_eval_items_idea ON domain_quality_eval_items(buildable_unit_id);

CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    embedding TEXT NOT NULL,
    PRIMARY KEY (id, entity_type)
);

CREATE TABLE IF NOT EXISTS publication_history (
    id TEXT PRIMARY KEY,
    idea_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    response_status INTEGER DEFAULT NULL,
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (idea_id) REFERENCES buildable_units(id)
);

CREATE INDEX IF NOT EXISTS idx_publication_history_idea ON publication_history(idea_id);
CREATE INDEX IF NOT EXISTS idx_publication_history_created ON publication_history(created_at);
"""


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add synthesized_at column to signals table."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "synthesized_at" not in columns:
        conn.execute("ALTER TABLE signals ADD COLUMN synthesized_at TEXT DEFAULT NULL")
        conn.commit()


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Add signal_role column to signals table."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "signal_role" not in columns:
        conn.execute("ALTER TABLE signals ADD COLUMN signal_role TEXT NOT NULL DEFAULT ''")
        conn.commit()


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Add pipeline_runs table and pipeline_run_id to feedback."""
    # Create pipeline_runs table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            config TEXT NOT NULL DEFAULT '{}',
            signals_fetched INTEGER NOT NULL DEFAULT 0,
            signals_new INTEGER NOT NULL DEFAULT 0,
            insights_generated INTEGER NOT NULL DEFAULT 0,
            ideas_generated INTEGER NOT NULL DEFAULT 0,
            ideas_evaluated INTEGER NOT NULL DEFAULT 0,
            specs_generated INTEGER NOT NULL DEFAULT 0,
            clusters_found INTEGER NOT NULL DEFAULT 0,
            gaps_detected INTEGER NOT NULL DEFAULT 0,
            avg_idea_score REAL NOT NULL DEFAULT 0.0,
            fetch_allocation TEXT NOT NULL DEFAULT '{}',
            token_usage TEXT NOT NULL DEFAULT '{}'
        )
    """)
    # Add pipeline_run_id to feedback
    columns = {row[1] for row in conn.execute("PRAGMA table_info(feedback)").fetchall()}
    if "pipeline_run_id" not in columns:
        conn.execute("ALTER TABLE feedback ADD COLUMN pipeline_run_id TEXT DEFAULT NULL")
    conn.commit()


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Add adapter_metrics column to pipeline_runs table."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)").fetchall()}
    if "adapter_metrics" not in columns:
        conn.execute(
            "ALTER TABLE pipeline_runs ADD COLUMN adapter_metrics TEXT NOT NULL DEFAULT '{}'"
        )
        conn.commit()


def _migrate_v5_to_v6(conn: sqlite3.Connection) -> None:
    """Add domain column to buildable_units table."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(buildable_units)").fetchall()}
    if "domain" not in columns:
        conn.execute(
            "ALTER TABLE buildable_units ADD COLUMN domain TEXT NOT NULL DEFAULT ''"
        )
        conn.commit()


def _migrate_v6_to_v7(conn: sqlite3.Connection) -> None:
    """Add pipeline_run_domains table for per-domain stats tracking."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_run_domains (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES pipeline_runs(id),
            domain TEXT NOT NULL,
            signals_fetched INTEGER DEFAULT 0,
            insights_generated INTEGER DEFAULT 0,
            ideas_generated INTEGER DEFAULT 0,
            ideas_evaluated INTEGER DEFAULT 0,
            avg_score REAL DEFAULT 0.0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_prd_run_id ON pipeline_run_domains(run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_prd_domain ON pipeline_run_domains(domain)"
    )
    conn.commit()


def _migrate_v7_to_v8(conn: sqlite3.Connection) -> None:
    """Add archived_at columns and indices for data retention."""
    # Add archived_at to signals
    columns = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "archived_at" not in columns:
        conn.execute("ALTER TABLE signals ADD COLUMN archived_at TEXT DEFAULT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_archived_at ON signals(archived_at)")

    # Add archived_at to insights
    columns = {row[1] for row in conn.execute("PRAGMA table_info(insights)").fetchall()}
    if "archived_at" not in columns:
        conn.execute("ALTER TABLE insights ADD COLUMN archived_at TEXT DEFAULT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_insights_archived_at ON insights(archived_at)")

    # Add archived_at to pipeline_runs
    columns = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)").fetchall()}
    if "archived_at" not in columns:
        conn.execute("ALTER TABLE pipeline_runs ADD COLUMN archived_at TEXT DEFAULT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_archived_at ON pipeline_runs(archived_at)")

    conn.commit()


def _migrate_v8_to_v9(conn: sqlite3.Connection) -> None:
    """Add prior_art_matches table and prior_art_status column."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prior_art_matches (
            id TEXT PRIMARY KEY,
            buildable_unit_id TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            relevance_score REAL NOT NULL DEFAULT 0.0,
            match_signals TEXT NOT NULL DEFAULT '{}',
            search_query TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_prior_art_bu_id ON prior_art_matches(buildable_unit_id)"
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(buildable_units)").fetchall()}
    if "prior_art_status" not in columns:
        conn.execute(
            "ALTER TABLE buildable_units ADD COLUMN prior_art_status TEXT NOT NULL DEFAULT 'unchecked'"
        )
    conn.commit()


def _migrate_v9_to_v10(conn: sqlite3.Connection) -> None:
    """Add source_idea_ids column to buildable_units for synthesis traceability."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(buildable_units)").fetchall()}
    if "source_idea_ids" not in columns:
        conn.execute(
            "ALTER TABLE buildable_units ADD COLUMN source_idea_ids TEXT NOT NULL DEFAULT '[]'"
        )
        conn.commit()


def _migrate_v10_to_v11(conn: sqlite3.Connection) -> None:
    """Drop tact_specs table — tact integration removed."""
    conn.execute("DROP TABLE IF EXISTS tact_specs")
    conn.commit()


def _migrate_v11_to_v12(conn: sqlite3.Connection) -> None:
    """Add approval_score column to feedback table."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(feedback)").fetchall()}
    if "approval_score" not in columns:
        conn.execute("ALTER TABLE feedback ADD COLUMN approval_score INTEGER DEFAULT NULL")
        conn.commit()


def _migrate_v12_to_v13(conn: sqlite3.Connection) -> None:
    """Add quality-loop fields to buildable_units."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(buildable_units)").fetchall()}
    additions = {
        "specific_user": "TEXT NOT NULL DEFAULT ''",
        "buyer": "TEXT NOT NULL DEFAULT ''",
        "workflow_context": "TEXT NOT NULL DEFAULT ''",
        "current_workaround": "TEXT NOT NULL DEFAULT ''",
        "why_now": "TEXT NOT NULL DEFAULT ''",
        "validation_plan": "TEXT NOT NULL DEFAULT ''",
        "first_10_customers": "TEXT NOT NULL DEFAULT ''",
        "domain_risks": "TEXT NOT NULL DEFAULT '[]'",
        "evidence_rationale": "TEXT NOT NULL DEFAULT ''",
        "novelty_score": "REAL NOT NULL DEFAULT 0.0",
        "usefulness_score": "REAL NOT NULL DEFAULT 0.0",
        "quality_score": "REAL NOT NULL DEFAULT 0.0",
        "rejection_tags": "TEXT NOT NULL DEFAULT '[]'",
    }
    changed = False
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE buildable_units ADD COLUMN {name} {ddl}")
            changed = True
    if changed:
        conn.commit()


def _migrate_v13_to_v14(conn: sqlite3.Connection) -> None:
    """Add persisted critique and idea-memory tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS idea_critiques (
            id TEXT PRIMARY KEY,
            buildable_unit_id TEXT NOT NULL,
            pipeline_run_id TEXT DEFAULT NULL,
            stage TEXT NOT NULL DEFAULT 'ideation_critique',
            dimensions TEXT NOT NULL DEFAULT '{}',
            reasoning TEXT NOT NULL DEFAULT '',
            rejection_tags TEXT NOT NULL DEFAULT '[]',
            evidence_pack TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_idea_critiques_bu_id ON idea_critiques(buildable_unit_id)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS idea_memory (
            id TEXT PRIMARY KEY,
            buildable_unit_id TEXT DEFAULT NULL,
            domain TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL,
            pattern TEXT NOT NULL,
            rejection_tags TEXT NOT NULL DEFAULT '[]',
            score REAL NOT NULL DEFAULT 0.0,
            evidence_rationale TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_idea_memory_domain ON idea_memory(domain)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_idea_memory_outcome ON idea_memory(outcome)")
    conn.commit()


def _migrate_v14_to_v15(conn: sqlite3.Connection) -> None:
    """Add pipeline run status and error text for failed-run inspection."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)").fetchall()}
    changed = False
    if "status" not in columns:
        conn.execute(
            "ALTER TABLE pipeline_runs ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'"
        )
        changed = True
    if "error_message" not in columns:
        conn.execute(
            "ALTER TABLE pipeline_runs ADD COLUMN error_message TEXT NOT NULL DEFAULT ''"
        )
        changed = True
    if changed:
        conn.commit()


def _migrate_v15_to_v16(conn: sqlite3.Connection) -> None:
    """Add persisted design brief tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS design_briefs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            domain TEXT NOT NULL DEFAULT '',
            theme TEXT NOT NULL DEFAULT '',
            readiness_score REAL NOT NULL DEFAULT 0.0,
            lead_idea_id TEXT NOT NULL,
            buyer TEXT NOT NULL DEFAULT '',
            specific_user TEXT NOT NULL DEFAULT '',
            workflow_context TEXT NOT NULL DEFAULT '',
            why_this_now TEXT NOT NULL DEFAULT '',
            merged_product_concept TEXT NOT NULL DEFAULT '',
            synthesis_rationale TEXT NOT NULL DEFAULT '',
            mvp_scope TEXT NOT NULL DEFAULT '[]',
            first_milestones TEXT NOT NULL DEFAULT '[]',
            validation_plan TEXT NOT NULL DEFAULT '',
            risks TEXT NOT NULL DEFAULT '[]',
            source_idea_ids TEXT NOT NULL DEFAULT '[]',
            design_status TEXT NOT NULL DEFAULT 'candidate',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (lead_idea_id) REFERENCES buildable_units(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS design_brief_sources (
            brief_id TEXT NOT NULL,
            idea_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'source',
            rank INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            PRIMARY KEY (brief_id, idea_id, role),
            FOREIGN KEY (brief_id) REFERENCES design_briefs(id),
            FOREIGN KEY (idea_id) REFERENCES buildable_units(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_design_briefs_domain ON design_briefs(domain)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_design_briefs_status ON design_briefs(design_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_design_brief_sources_idea ON design_brief_sources(idea_id)")
    conn.commit()


def _migrate_v16_to_v17(conn: sqlite3.Connection) -> None:
    """Add domain quality score and memory tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS domain_quality_scores (
            id TEXT PRIMARY KEY,
            buildable_unit_id TEXT NOT NULL,
            domain TEXT NOT NULL DEFAULT '',
            profile_name TEXT NOT NULL DEFAULT '',
            rubric_version TEXT NOT NULL DEFAULT 'v1',
            dimensions TEXT NOT NULL DEFAULT '{}',
            overall_score REAL NOT NULL DEFAULT 0.0,
            passed_gate INTEGER NOT NULL DEFAULT 0,
            rejection_tags TEXT NOT NULL DEFAULT '[]',
            reasoning TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS domain_quality_memory (
            id TEXT PRIMARY KEY,
            domain TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL,
            pattern TEXT NOT NULL,
            source_idea_id TEXT DEFAULT NULL,
            source_design_brief_id TEXT DEFAULT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            score REAL NOT NULL DEFAULT 0.0,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (source_idea_id) REFERENCES buildable_units(id),
            FOREIGN KEY (source_design_brief_id) REFERENCES design_briefs(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_domain_quality_scores_unit ON domain_quality_scores(buildable_unit_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_domain_quality_scores_domain ON domain_quality_scores(domain)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_domain_quality_memory_domain ON domain_quality_memory(domain)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_domain_quality_memory_outcome ON domain_quality_memory(outcome)"
    )
    conn.commit()


def _migrate_v17_to_v18(conn: sqlite3.Connection) -> None:
    """Add domain quality eval run tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS domain_quality_eval_runs (
            id TEXT PRIMARY KEY,
            profile_name TEXT NOT NULL DEFAULT '',
            domain TEXT NOT NULL DEFAULT '',
            rubric_version TEXT NOT NULL DEFAULT 'v1',
            baseline_pipeline_run_id TEXT NOT NULL DEFAULT '',
            rubric_pipeline_run_id TEXT NOT NULL DEFAULT '',
            baseline_ideas INTEGER NOT NULL DEFAULT 0,
            rubric_ideas INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS domain_quality_eval_items (
            id TEXT PRIMARY KEY,
            eval_run_id TEXT NOT NULL,
            buildable_unit_id TEXT NOT NULL,
            cohort TEXT NOT NULL,
            domain_quality_score REAL DEFAULT NULL,
            passed_gate INTEGER DEFAULT NULL,
            evaluation_score REAL DEFAULT NULL,
            review_outcome TEXT DEFAULT NULL,
            approval_score INTEGER DEFAULT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (eval_run_id) REFERENCES domain_quality_eval_runs(id),
            FOREIGN KEY (buildable_unit_id) REFERENCES buildable_units(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_domain_quality_eval_items_run ON domain_quality_eval_items(eval_run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_domain_quality_eval_items_idea ON domain_quality_eval_items(buildable_unit_id)"
    )
    conn.commit()


def _migrate_v18_to_v19(conn: sqlite3.Connection) -> None:
    """Add publication attempt history table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS publication_history (
            id TEXT PRIMARY KEY,
            idea_id TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            response_status INTEGER DEFAULT NULL,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (idea_id) REFERENCES buildable_units(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publication_history_idea ON publication_history(idea_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publication_history_created ON publication_history(created_at)"
    )
    conn.commit()


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist, apply migrations if needed."""
    conn.executescript(SCHEMA_SQL)

    cursor = conn.execute("SELECT COUNT(*) FROM schema_version")
    if cursor.fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        # Create archived_at indices for fresh DB
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_archived_at ON signals(archived_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_insights_archived_at ON insights(archived_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_archived_at ON pipeline_runs(archived_at)")
        conn.commit()
        return

    current = conn.execute("SELECT version FROM schema_version").fetchone()[0]

    if current < 2:
        _migrate_v1_to_v2(conn)

    if current < 3:
        _migrate_v2_to_v3(conn)

    if current < 4:
        _migrate_v3_to_v4(conn)

    if current < 5:
        _migrate_v4_to_v5(conn)

    if current < 6:
        _migrate_v5_to_v6(conn)

    if current < 7:
        _migrate_v6_to_v7(conn)

    if current < 8:
        _migrate_v7_to_v8(conn)

    if current < 9:
        _migrate_v8_to_v9(conn)

    if current < 10:
        _migrate_v9_to_v10(conn)

    if current < 11:
        _migrate_v10_to_v11(conn)

    if current < 12:
        _migrate_v11_to_v12(conn)

    if current < 13:
        _migrate_v12_to_v13(conn)

    if current < 14:
        _migrate_v13_to_v14(conn)

    if current < 15:
        _migrate_v14_to_v15(conn)

    if current < 16:
        _migrate_v15_to_v16(conn)

    if current < 17:
        _migrate_v16_to_v17(conn)

    if current < 18:
        _migrate_v17_to_v18(conn)

    if current < 19:
        _migrate_v18_to_v19(conn)

    if current < SCHEMA_VERSION:
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
        conn.commit()

    # Create archived_at indices (safe to run multiple times due to IF NOT EXISTS)
    # These are separate from SCHEMA_SQL to avoid errors during migration when columns don't exist yet
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_archived_at ON signals(archived_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_insights_archived_at ON insights(archived_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_archived_at ON pipeline_runs(archived_at)")
    conn.commit()
