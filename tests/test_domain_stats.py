"""Tests for per-domain pipeline run statistics.

Covers:
- Migration v6→v7 creates pipeline_run_domains table
- Store CRUD: insert_pipeline_run_domain, get_pipeline_run_domains, get_domain_performance
- Pipeline runner records domain stats when ideas have domains set
- Empty domain ('') ideas are still tracked
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

from max.store.db import Store
from max.store.migrations import SCHEMA_VERSION, ensure_schema
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_unit(
    unit_id: str = "bu-test001",
    domain: str = "",
) -> BuildableUnit:
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
        domain=domain,
    )


def _make_score(value: float = 7.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _make_evaluation(unit_id: str = "bu-test001", overall_score: float = 72.0) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_make_score(8.0),
        addressable_scale=_make_score(7.0),
        build_effort=_make_score(6.0),
        composability=_make_score(7.5),
        competitive_density=_make_score(8.0),
        timing_fit=_make_score(7.0),
        compounding_value=_make_score(6.5),
        overall_score=overall_score,
        strengths=["test"],
        weaknesses=["test"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )


# ── Migration tests ──────────────────────────────────────────────────


class TestMigration:
    def test_schema_version_is_18(self) -> None:
        assert SCHEMA_VERSION == 18

    def test_fresh_schema_creates_pipeline_run_domains_table(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "fresh.db")
        conn = sqlite3.connect(db_path)
        ensure_schema(conn)

        # Table exists
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pipeline_run_domains" in tables

        # Columns are correct
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(pipeline_run_domains)").fetchall()
        }
        expected = {
            "id", "run_id", "domain", "signals_fetched", "insights_generated",
            "ideas_generated", "ideas_evaluated", "avg_score", "created_at",
        }
        assert columns == expected

        # Indexes exist
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='pipeline_run_domains'"
            ).fetchall()
        }
        assert "idx_prd_run_id" in indexes
        assert "idx_prd_domain" in indexes

        conn.close()

    def test_migration_from_v6_creates_table(self, tmp_path: Path) -> None:
        """Simulate a v6 database and verify migration to v7 adds the table."""
        db_path = str(tmp_path / "v6.db")
        conn = sqlite3.connect(db_path)

        # Bootstrap a minimal v6 schema
        conn.executescript("""
            CREATE TABLE schema_version (version INTEGER NOT NULL);
            INSERT INTO schema_version (version) VALUES (6);
            CREATE TABLE pipeline_runs (
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
                token_usage TEXT NOT NULL DEFAULT '{}',
                adapter_metrics TEXT NOT NULL DEFAULT '{}'
            );
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
                metadata TEXT NOT NULL DEFAULT '{}',
                synthesized_at TEXT DEFAULT NULL,
                signal_role TEXT NOT NULL DEFAULT ''
            );
            CREATE UNIQUE INDEX idx_signals_url ON signals(url);
            CREATE TABLE insights (
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
            CREATE TABLE buildable_units (
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
                domain TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE evaluations (
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
                weights_used TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buildable_unit_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                dimension_values TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                pipeline_run_id TEXT DEFAULT NULL
            );
            CREATE TABLE embeddings (
                id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                embedding TEXT NOT NULL,
                PRIMARY KEY (id, entity_type)
            );
        """)

        # Verify table doesn't exist yet
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pipeline_run_domains" not in tables

        # Run ensure_schema which should apply migration
        ensure_schema(conn)

        # Verify table now exists
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pipeline_run_domains" in tables

        # Verify version is updated
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == 18

        conn.close()


# ── Store method tests ────────────────────────────────────────────────


class TestInsertPipelineRunDomain:
    def test_inserts_row(self, store: Store) -> None:
        store.insert_pipeline_run("run-001", {"profile": "test"})
        store.insert_pipeline_run_domain("run-001", "healthcare", {
            "signals_fetched": 10,
            "insights_generated": 3,
            "ideas_generated": 5,
            "ideas_evaluated": 4,
            "avg_score": 72.5,
        })

        domains = store.get_pipeline_run_domains("run-001")
        assert len(domains) == 1
        d = domains[0]
        assert d["run_id"] == "run-001"
        assert d["domain"] == "healthcare"
        assert d["signals_fetched"] == 10
        assert d["insights_generated"] == 3
        assert d["ideas_generated"] == 5
        assert d["ideas_evaluated"] == 4
        assert d["avg_score"] == 72.5
        assert d["id"].startswith("prd-")
        assert d["created_at"] is not None

    def test_defaults_for_missing_stats(self, store: Store) -> None:
        store.insert_pipeline_run("run-002", {})
        store.insert_pipeline_run_domain("run-002", "fintech", {})

        domains = store.get_pipeline_run_domains("run-002")
        assert len(domains) == 1
        d = domains[0]
        assert d["signals_fetched"] == 0
        assert d["insights_generated"] == 0
        assert d["ideas_generated"] == 0
        assert d["ideas_evaluated"] == 0
        assert d["avg_score"] == 0.0

    def test_multiple_domains_per_run(self, store: Store) -> None:
        store.insert_pipeline_run("run-003", {})
        store.insert_pipeline_run_domain("run-003", "healthcare", {"ideas_generated": 3})
        store.insert_pipeline_run_domain("run-003", "fintech", {"ideas_generated": 2})
        store.insert_pipeline_run_domain("run-003", "", {"ideas_generated": 1})

        domains = store.get_pipeline_run_domains("run-003")
        assert len(domains) == 3
        domain_map = {d["domain"]: d for d in domains}
        assert domain_map["healthcare"]["ideas_generated"] == 3
        assert domain_map["fintech"]["ideas_generated"] == 2
        assert domain_map[""]["ideas_generated"] == 1


class TestGetPipelineRunDomains:
    def test_returns_empty_for_unknown_run(self, store: Store) -> None:
        assert store.get_pipeline_run_domains("run-nonexistent") == []

    def test_ordered_by_domain_name(self, store: Store) -> None:
        store.insert_pipeline_run("run-004", {})
        store.insert_pipeline_run_domain("run-004", "zebra", {"ideas_generated": 1})
        store.insert_pipeline_run_domain("run-004", "alpha", {"ideas_generated": 2})
        store.insert_pipeline_run_domain("run-004", "middle", {"ideas_generated": 3})

        domains = store.get_pipeline_run_domains("run-004")
        assert [d["domain"] for d in domains] == ["alpha", "middle", "zebra"]


class TestGetDomainPerformance:
    def test_returns_recent_runs_for_domain(self, store: Store) -> None:
        for i in range(3):
            store.insert_pipeline_run(f"run-perf-{i}", {})
            store.insert_pipeline_run_domain(
                f"run-perf-{i}", "healthcare", {"ideas_generated": i + 1}
            )

        perf = store.get_domain_performance("healthcare")
        assert len(perf) == 3
        # Most recent run first (descending by run's started_at)
        assert perf[0]["run_id"] == "run-perf-2"
        assert perf[0]["ideas_generated"] == 3
        assert perf[2]["run_id"] == "run-perf-0"
        assert perf[2]["ideas_generated"] == 1

    def test_respects_limit(self, store: Store) -> None:
        for i in range(5):
            store.insert_pipeline_run(f"run-lim-{i}", {})
            store.insert_pipeline_run_domain(f"run-lim-{i}", "fintech", {"ideas_generated": i})

        perf = store.get_domain_performance("fintech", limit=3)
        assert len(perf) == 3

    def test_returns_empty_for_unknown_domain(self, store: Store) -> None:
        assert store.get_domain_performance("nonexistent") == []

    def test_filters_by_domain(self, store: Store) -> None:
        store.insert_pipeline_run("run-filt-1", {})
        store.insert_pipeline_run_domain("run-filt-1", "healthcare", {"ideas_generated": 5})
        store.insert_pipeline_run_domain("run-filt-1", "fintech", {"ideas_generated": 3})

        hc = store.get_domain_performance("healthcare")
        assert len(hc) == 1
        assert hc[0]["domain"] == "healthcare"

        ft = store.get_domain_performance("fintech")
        assert len(ft) == 1
        assert ft[0]["domain"] == "fintech"

    def test_includes_run_started_at(self, store: Store) -> None:
        store.insert_pipeline_run("run-ts-1", {})
        store.insert_pipeline_run_domain("run-ts-1", "healthcare", {})

        perf = store.get_domain_performance("healthcare")
        assert len(perf) == 1
        assert perf[0]["run_started_at"] is not None

    def test_empty_domain_tracked(self, store: Store) -> None:
        store.insert_pipeline_run("run-empty-d", {})
        store.insert_pipeline_run_domain("run-empty-d", "", {"ideas_generated": 2})

        perf = store.get_domain_performance("")
        assert len(perf) == 1
        assert perf[0]["ideas_generated"] == 2


# ── Pipeline runner integration ───────────────────────────────────────


def _mock_hn_item(story_id: int, title: str) -> dict:
    return {
        "id": story_id, "type": "story", "title": title,
        "url": f"https://example.com/{story_id}", "by": "user",
        "time": 1711000000, "score": 200, "descendants": 30,
    }


def _make_store(db_path: str) -> Store:
    return Store(db_path=db_path)


class TestPipelineRunnerDomainStats:
    def test_records_domain_stats_with_profile(self, tmp_path: Path) -> None:
        """Pipeline records per-domain stats when ideas have domain set."""
        from max.pipeline.runner import run_pipeline
        from max.profiles.schema import DomainContext, EvaluationConfig, PipelineProfile, SourceConfig
        from max.synthesis.engine import SynthesisOutput, InsightOutput
        from max.ideation.engine import IdeationOutput, BuildableUnitOutput
        from max.evaluation.engine import EvaluationOutput, DimensionScoreOutput
        db_path = str(tmp_path / "test_domain_stats.db")

        def score(v: float) -> DimensionScoreOutput:
            return DimensionScoreOutput(value=v, confidence=0.7, reasoning="Mock")

        def mock_structured_call(system, prompt, output_type, **kwargs):
            type_name = output_type.__name__
            if type_name == "SynthesisOutput":
                return SynthesisOutput(insights=[
                    InsightOutput(
                        category="gap", title="Test insight", summary="Summary",
                        evidence=["sig-mock001"], confidence=0.85,
                        domains=["healthcare"], implications=["Needs fixing"],
                        time_horizon="near_term",
                    ),
                ])
            elif type_name == "IdeationOutput":
                return IdeationOutput(ideas=[
                    BuildableUnitOutput(
                        title="Health Tool", one_liner="A health tool",
                        category="cli_tool", problem="Problem",
                        solution="Solution", target_users="both",
                        value_proposition="Value",
                        inspiring_insights=["ins-mock001"],
                        tech_approach="Python", suggested_stack={"language": "python"},
                        composability_notes="Notes",
                    ),
                ])
            elif type_name == "EvaluationOutput":
                return EvaluationOutput(
                    pain_severity=score(8.0), addressable_scale=score(7.0),
                    build_effort=score(7.5), composability=score(8.5),
                    competitive_density=score(9.0), timing_fit=score(8.0),
                    compounding_value=score(7.0),
                    strengths=["Good"], weaknesses=["Bad"],
                    recommendation="yes",
                )
            raise ValueError(f"Unexpected: {type_name}")

        profile = PipelineProfile(
            name="healthcare",
            domain=DomainContext(
                name="healthcare",
                description="Healthcare tech",
                categories=["cli_tool"],
                target_user_types=["clinicians"],
            ),
            sources=[SourceConfig(adapter="hackernews")],
            evaluation=EvaluationConfig(min_score=40.0),
            signal_limit=5,
        )

        mock_signals = [
            Signal(
                id="sig-mock001",
                source_type=SignalSourceType.FORUM,
                source_adapter="hackernews",
                title="Health data discussion",
                content="Content about health data.",
                url="https://example.com/health",
                credibility=0.7,
            ),
        ]

        with (
            patch("max.pipeline.runner._fetch_all_signals", return_value=(mock_signals, {"hackernews": 5}, {})),
            patch("max.llm.client.get_client"),
            patch("max.synthesis.engine.structured_call", side_effect=mock_structured_call),
            patch("max.ideation.engine.structured_call", side_effect=mock_structured_call),
            patch("max.evaluation.engine.structured_call", side_effect=mock_structured_call),
            patch("max.store.db.DB_PATH", db_path),
            patch("max.pipeline.runner.Store", lambda: _make_store(db_path)),
        ):
            result = run_pipeline(profile=profile)

        # Verify pipeline completed
        assert result.ideas_generated == 1
        assert result.ideas_evaluated == 1

        # Verify domain stats were recorded
        store = Store(db_path=db_path)
        try:
            domains = store.get_pipeline_run_domains(result.run_id)
            assert len(domains) == 1
            d = domains[0]
            assert d["domain"] == "healthcare"
            assert d["ideas_generated"] == 1
            assert d["ideas_evaluated"] == 1
            assert d["avg_score"] > 0
        finally:
            store.close()

    def test_records_empty_domain_stats(self, tmp_path: Path) -> None:
        """Pipeline records domain stats for ideas with no domain (empty string)."""
        from max.pipeline.runner import run_pipeline
        from max.synthesis.engine import SynthesisOutput, InsightOutput
        from max.ideation.engine import IdeationOutput, BuildableUnitOutput
        from max.evaluation.engine import EvaluationOutput, DimensionScoreOutput
        db_path = str(tmp_path / "test_empty_domain.db")

        def score(v: float) -> DimensionScoreOutput:
            return DimensionScoreOutput(value=v, confidence=0.7, reasoning="Mock")

        def mock_structured_call(system, prompt, output_type, **kwargs):
            type_name = output_type.__name__
            if type_name == "SynthesisOutput":
                return SynthesisOutput(insights=[
                    InsightOutput(
                        category="gap", title="Test insight", summary="Summary",
                        evidence=[], confidence=0.85, domains=[], implications=[],
                        time_horizon="near_term",
                    ),
                ])
            elif type_name == "IdeationOutput":
                return IdeationOutput(ideas=[
                    BuildableUnitOutput(
                        title="Generic Tool", one_liner="A tool",
                        category="cli_tool", problem="Problem",
                        solution="Solution", target_users="both",
                        value_proposition="Value",
                        inspiring_insights=[],
                        tech_approach="Python", suggested_stack={},
                        composability_notes="",
                    ),
                ])
            elif type_name == "EvaluationOutput":
                return EvaluationOutput(
                    pain_severity=score(8.0), addressable_scale=score(7.0),
                    build_effort=score(7.5), composability=score(8.5),
                    competitive_density=score(9.0), timing_fit=score(8.0),
                    compounding_value=score(7.0),
                    strengths=["Good"], weaknesses=["Bad"],
                    recommendation="yes",
                )
            raise ValueError(f"Unexpected: {type_name}")

        mock_signals = [
            Signal(
                id="sig-nodom",
                source_type=SignalSourceType.FORUM,
                source_adapter="hackernews",
                title="Generic discussion",
                content="Some content.",
                url="https://example.com/generic",
                credibility=0.7,
            ),
        ]

        with (
            patch("max.pipeline.runner._fetch_all_signals", return_value=(mock_signals, {"hackernews": 5}, {})),
            patch("max.llm.client.get_client"),
            patch("max.synthesis.engine.structured_call", side_effect=mock_structured_call),
            patch("max.ideation.engine.structured_call", side_effect=mock_structured_call),
            patch("max.evaluation.engine.structured_call", side_effect=mock_structured_call),
            patch("max.store.db.DB_PATH", db_path),
            patch("max.pipeline.runner.Store", lambda: _make_store(db_path)),
        ):
            # No profile → domain is empty string
            result = run_pipeline(output_dir=None, signal_limit=5, min_score=40.0)

        assert result.ideas_generated == 1

        store = Store(db_path=db_path)
        try:
            domains = store.get_pipeline_run_domains(result.run_id)
            assert len(domains) == 1
            assert domains[0]["domain"] == ""
            assert domains[0]["ideas_generated"] == 1
        finally:
            store.close()
