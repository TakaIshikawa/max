"""SQLite Store — CRUD for all max entities."""

from __future__ import annotations

import base64
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from max.config import DB_PATH
from max.store.migrations import ensure_schema
from max.types.signal import Signal
from max.types.insight import Insight
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation, DimensionScore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _encode_cursor(timestamp: str, entity_id: str) -> str:
    """Encode (timestamp, id) as base64 cursor."""
    cursor_data = f"{timestamp}|{entity_id}"
    return base64.b64encode(cursor_data.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    """Decode base64 cursor to (timestamp, id)."""
    try:
        cursor_data = base64.b64decode(cursor.encode()).decode()
        timestamp, entity_id = cursor_data.split("|", 1)
        return timestamp, entity_id
    except Exception:
        raise ValueError("Invalid cursor format")


class Store:
    """Single-connection SQLite store for max entities."""

    def __init__(self, db_path: str = DB_PATH, *, wal_mode: bool = False):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        if wal_mode:
            self.conn.execute("PRAGMA journal_mode=WAL")
        ensure_schema(self.conn)

    def __enter__(self) -> Store:
        """Enter context manager - returns self."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit context manager - close connection and don't suppress exceptions."""
        self.close()
        return False  # Don't suppress exceptions

    def close(self) -> None:
        self.conn.close()

    def _commit(self) -> None:
        """Commit unless we're in a transaction context."""
        if not getattr(self, "_in_transaction", False):
            self.conn.commit()

    def transaction(self):
        """Context manager for atomic transactions.

        Usage:
            with store.transaction():
                store.insert_signal(signal)
                store.update_buildable_unit_status(unit_id, "evaluated")

        Commits on success, rolls back on exception.

        Note: This temporarily disables auto-commit behavior of Store methods.
        All commits within the transaction block are deferred until the transaction completes.
        """
        from contextlib import contextmanager

        @contextmanager
        def _transaction():
            # Mark that we're in a transaction to prevent auto-commits
            # We'll use a flag to track this
            was_in_transaction = getattr(self, "_in_transaction", False)
            self._in_transaction = True

            # Save current isolation level and start transaction
            old_isolation = self.conn.isolation_level
            self.conn.isolation_level = None  # autocommit mode off

            try:
                self.conn.execute("BEGIN")
                yield
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                self.conn.isolation_level = old_isolation
                self._in_transaction = was_in_transaction

        return _transaction()

    def get_schema_version(self) -> int:
        row = self.conn.execute("SELECT version FROM schema_version").fetchone()
        return row[0] if row else 0

    # ── Signals ──────────────────────────────────────────────────────

    def insert_signal(self, signal: Signal) -> Signal:
        if not signal.id:
            signal.id = _gen_id("sig")
        try:
            self.conn.execute(
                """INSERT INTO signals
                   (id, source_type, source_adapter, title, content, url,
                    author, published_at, fetched_at, tags, credibility, metadata,
                    signal_role)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal.id,
                    signal.source_type.value,
                    signal.source_adapter,
                    signal.title,
                    signal.content,
                    signal.url,
                    signal.author,
                    signal.published_at.isoformat() if signal.published_at else None,
                    signal.fetched_at.isoformat(),
                    json.dumps(signal.tags),
                    signal.credibility,
                    json.dumps(signal.metadata),
                    signal.metadata.get("signal_role", ""),
                ),
            )
            self._commit()
        except sqlite3.IntegrityError:
            pass  # duplicate URL — skip
        return signal

    def get_signals(self, *, limit: int = 100, source_type: str | None = None) -> list[Signal]:
        query = "SELECT * FROM signals WHERE archived_at IS NULL"
        params: list = []
        if source_type:
            query += " AND source_type = ?"
            params.append(source_type)
        query += " ORDER BY fetched_at DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_signal(row) for row in rows]

    def get_signals_paginated(
        self, *, cursor: str | None = None, limit: int = 20, source_type: str | None = None
    ) -> tuple[list[Signal], str | None]:
        """Get signals with cursor-based pagination.

        Returns (signals, next_cursor). Cursor is None if no more results.
        """
        query = "SELECT * FROM signals"
        params: list = []
        conditions: list[str] = []

        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)

        if cursor:
            cursor_timestamp, cursor_id = _decode_cursor(cursor)
            conditions.append("(fetched_at, id) < (?, ?)")
            params.extend([cursor_timestamp, cursor_id])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY fetched_at DESC, id DESC LIMIT ?"
        params.append(limit + 1)  # Fetch one extra to determine if there are more results

        rows = self.conn.execute(query, params).fetchall()
        signals = [_row_to_signal(row) for row in rows]

        # Check if there are more results
        has_more = len(signals) > limit
        if has_more:
            signals = signals[:limit]

        # Generate next cursor from the last item
        next_cursor = None
        if has_more and signals:
            last_signal = signals[-1]
            next_cursor = _encode_cursor(last_signal.fetched_at.isoformat(), last_signal.id)

        return signals, next_cursor

    def count_signals(self, *, source_type: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM signals"
        params: list = []
        if source_type:
            query += " WHERE source_type = ?"
            params.append(source_type)
        return self.conn.execute(query, params).fetchone()[0]

    def get_unsynthesized_signals(self, *, limit: int = 100) -> list[Signal]:
        """Get signals that have not yet been synthesized."""
        rows = self.conn.execute(
            """SELECT * FROM signals
               WHERE synthesized_at IS NULL AND archived_at IS NULL
               ORDER BY fetched_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [_row_to_signal(row) for row in rows]

    def mark_signals_synthesized(self, signal_ids: list[str]) -> None:
        """Mark signals as synthesized with current timestamp."""
        if not signal_ids:
            return
        now = _now_iso()
        self.conn.executemany(
            "UPDATE signals SET synthesized_at = ? WHERE id = ?",
            [(now, sid) for sid in signal_ids],
        )
        self._commit()

    def get_signal(self, signal_id: str) -> Signal | None:
        """Get a single signal by ID."""
        row = self.conn.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()
        return _row_to_signal(row) if row else None

    def update_signal_role(self, signal_id: str, role: str) -> None:
        """Update the signal_role for a signal."""
        self.conn.execute(
            "UPDATE signals SET signal_role = ? WHERE id = ?",
            (role, signal_id),
        )
        self._commit()

    def get_signals_by_role(self, role: str, *, limit: int = 100) -> list[Signal]:
        """Get signals filtered by signal_role."""
        rows = self.conn.execute(
            """SELECT * FROM signals
               WHERE signal_role = ? AND archived_at IS NULL
               ORDER BY fetched_at DESC LIMIT ?""",
            (role, limit),
        ).fetchall()
        return [_row_to_signal(row) for row in rows]

    def get_adapter_quality_stats(self) -> dict[str, dict]:
        """Get per-adapter signal utilization stats.

        Returns dict[adapter_name, {total_signals, insight_hit_rate, idea_hit_rate}].
        """
        rows = self.conn.execute(
            """SELECT source_adapter, COUNT(*) as cnt
               FROM signals WHERE archived_at IS NULL
               GROUP BY source_adapter"""
        ).fetchall()
        stats: dict[str, dict] = {}
        for row in rows:
            stats[row["source_adapter"]] = {
                "total_signals": row["cnt"],
                "insight_hit_rate": 0.0,
                "idea_hit_rate": 0.0,
            }

        # Collect signal IDs referenced in insights
        insight_rows = self.conn.execute("SELECT evidence FROM insights").fetchall()
        insight_signal_ids: set[str] = set()
        for row in insight_rows:
            ids = json.loads(row["evidence"])
            insight_signal_ids.update(ids)

        # Collect signal IDs referenced in buildable units
        unit_rows = self.conn.execute(
            "SELECT evidence_signals FROM buildable_units"
        ).fetchall()
        idea_signal_ids: set[str] = set()
        for row in unit_rows:
            ids = json.loads(row["evidence_signals"])
            idea_signal_ids.update(ids)

        # Map signal IDs back to adapters
        all_ids = insight_signal_ids | idea_signal_ids
        if all_ids:
            placeholders = ",".join("?" for _ in all_ids)
            id_rows = self.conn.execute(
                f"SELECT id, source_adapter FROM signals WHERE id IN ({placeholders})",
                list(all_ids),
            ).fetchall()

            adapter_insight_hits: dict[str, int] = {}
            adapter_idea_hits: dict[str, int] = {}
            for row in id_rows:
                adapter = row["source_adapter"]
                if row["id"] in insight_signal_ids:
                    adapter_insight_hits[adapter] = adapter_insight_hits.get(adapter, 0) + 1
                if row["id"] in idea_signal_ids:
                    adapter_idea_hits[adapter] = adapter_idea_hits.get(adapter, 0) + 1

            for adapter, s in stats.items():
                total = s["total_signals"]
                if total > 0:
                    s["insight_hit_rate"] = adapter_insight_hits.get(adapter, 0) / total
                    s["idea_hit_rate"] = adapter_idea_hits.get(adapter, 0) / total

        return stats

    # ── Insights ─────────────────────────────────────────────────────

    def insert_insight(self, insight: Insight) -> Insight:
        if not insight.id:
            insight.id = _gen_id("ins")
        self.conn.execute(
            """INSERT INTO insights
               (id, category, title, summary, evidence, confidence,
                domains, implications, time_horizon, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                insight.id,
                insight.category.value,
                insight.title,
                insight.summary,
                json.dumps(insight.evidence),
                insight.confidence,
                json.dumps(insight.domains),
                json.dumps(insight.implications),
                insight.time_horizon,
                insight.created_at.isoformat(),
            ),
        )
        self._commit()
        return insight

    def get_insights(self, *, limit: int = 100) -> list[Insight]:
        rows = self.conn.execute(
            """SELECT * FROM insights WHERE archived_at IS NULL
               ORDER BY created_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [_row_to_insight(row) for row in rows]

    def get_insights_paginated(
        self, *, cursor: str | None = None, limit: int = 20
    ) -> tuple[list[Insight], str | None]:
        """Get insights with cursor-based pagination.

        Returns (insights, next_cursor). Cursor is None if no more results.
        """
        query = "SELECT * FROM insights"
        params: list = []

        if cursor:
            cursor_timestamp, cursor_id = _decode_cursor(cursor)
            query += " WHERE (created_at, id) < (?, ?)"
            params.extend([cursor_timestamp, cursor_id])

        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit + 1)

        rows = self.conn.execute(query, params).fetchall()
        insights = [_row_to_insight(row) for row in rows]

        has_more = len(insights) > limit
        if has_more:
            insights = insights[:limit]

        next_cursor = None
        if has_more and insights:
            last_insight = insights[-1]
            next_cursor = _encode_cursor(last_insight.created_at.isoformat(), last_insight.id)

        return insights, next_cursor

    def get_insight(self, insight_id: str) -> Insight | None:
        """Get a single insight by ID."""
        row = self.conn.execute(
            "SELECT * FROM insights WHERE id = ?", (insight_id,)
        ).fetchone()
        return _row_to_insight(row) if row else None

    def count_insights(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM insights").fetchone()[0]

    # ── BuildableUnits ───────────────────────────────────────────────

    def insert_buildable_unit(self, unit: BuildableUnit) -> BuildableUnit:
        if not unit.id:
            unit.id = _gen_id("bu")
        self.conn.execute(
            """INSERT INTO buildable_units
               (id, title, one_liner, category, ideation_mode, problem, solution,
                target_users, value_proposition, specific_user, buyer, workflow_context,
                current_workaround, why_now, validation_plan, first_10_customers,
                domain_risks, evidence_rationale, novelty_score, usefulness_score,
                quality_score, rejection_tags, inspiring_insights, evidence_signals,
                tech_approach, suggested_stack, composability_notes, status, domain,
                source_idea_ids, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                unit.id,
                unit.title,
                unit.one_liner,
                unit.category,
                unit.ideation_mode.value,
                unit.problem,
                unit.solution,
                unit.target_users,
                unit.value_proposition,
                unit.specific_user,
                unit.buyer,
                unit.workflow_context,
                unit.current_workaround,
                unit.why_now,
                unit.validation_plan,
                unit.first_10_customers,
                json.dumps(unit.domain_risks),
                unit.evidence_rationale,
                unit.novelty_score,
                unit.usefulness_score,
                unit.quality_score,
                json.dumps(unit.rejection_tags),
                json.dumps(unit.inspiring_insights),
                json.dumps(unit.evidence_signals),
                unit.tech_approach,
                json.dumps(unit.suggested_stack),
                unit.composability_notes,
                unit.status,
                unit.domain,
                json.dumps(unit.source_idea_ids),
                unit.created_at.isoformat(),
                unit.updated_at.isoformat(),
            ),
        )
        self._commit()
        return unit

    def get_buildable_unit(self, unit_id: str) -> BuildableUnit | None:
        row = self.conn.execute(
            "SELECT * FROM buildable_units WHERE id = ?", (unit_id,)
        ).fetchone()
        return _row_to_buildable_unit(row) if row else None

    def get_buildable_units(
        self, *, limit: int = 100, status: str | None = None, domain: str | None = None,
    ) -> list[BuildableUnit]:
        query = "SELECT * FROM buildable_units"
        conditions: list[str] = []
        params: list = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_buildable_unit(row) for row in rows]

    def get_buildable_units_paginated(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: str | None = None,
        domain: str | None = None,
    ) -> tuple[list[BuildableUnit], str | None]:
        """Get buildable units with cursor-based pagination.

        Returns (units, next_cursor). Cursor is None if no more results.
        """
        query = "SELECT * FROM buildable_units"
        conditions: list[str] = []
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if cursor:
            cursor_timestamp, cursor_id = _decode_cursor(cursor)
            conditions.append("(updated_at, id) < (?, ?)")
            params.extend([cursor_timestamp, cursor_id])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(limit + 1)

        rows = self.conn.execute(query, params).fetchall()
        units = [_row_to_buildable_unit(row) for row in rows]

        has_more = len(units) > limit
        if has_more:
            units = units[:limit]

        next_cursor = None
        if has_more and units:
            last_unit = units[-1]
            next_cursor = _encode_cursor(last_unit.updated_at.isoformat(), last_unit.id)

        return units, next_cursor

    def update_buildable_unit_status(self, unit_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE buildable_units SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now_iso(), unit_id),
        )
        self._commit()

    def count_buildable_units(self, *, status: str | None = None, domain: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM buildable_units"
        conditions: list[str] = []
        params: list = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        return self.conn.execute(query, params).fetchone()[0]

    # ── Prior Art ───────────────────────────────────────────────────

    def insert_prior_art_match(self, unit_id: str, match: dict) -> str:
        match_id = _gen_id("pa")
        self.conn.execute(
            """INSERT INTO prior_art_matches
               (id, buildable_unit_id, source, title, url, description,
                relevance_score, match_signals, search_query, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                match_id,
                unit_id,
                match["source"],
                match["title"],
                match["url"],
                match.get("description", ""),
                match.get("relevance_score", 0.0),
                json.dumps(match.get("match_signals", {})),
                match.get("search_query", ""),
                _now_iso(),
            ),
        )
        self._commit()
        return match_id

    def get_prior_art_matches(self, unit_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM prior_art_matches WHERE buildable_unit_id = ? ORDER BY relevance_score DESC",
            (unit_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "buildable_unit_id": row["buildable_unit_id"],
                "source": row["source"],
                "title": row["title"],
                "url": row["url"],
                "description": row["description"],
                "relevance_score": row["relevance_score"],
                "match_signals": json.loads(row["match_signals"]),
                "search_query": row["search_query"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def update_prior_art_status(self, unit_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE buildable_units SET prior_art_status = ?, updated_at = ? WHERE id = ?",
            (status, _now_iso(), unit_id),
        )
        self._commit()

    def delete_prior_art_matches(self, unit_id: str) -> int:
        cursor = self.conn.execute(
            "DELETE FROM prior_art_matches WHERE buildable_unit_id = ?",
            (unit_id,),
        )
        self._commit()
        return cursor.rowcount

    # ── Evaluations ──────────────────────────────────────────────────

    def insert_evaluation(self, evaluation: UtilityEvaluation) -> UtilityEvaluation:
        self.conn.execute(
            """INSERT OR REPLACE INTO evaluations
               (buildable_unit_id, pain_severity, addressable_scale, build_effort,
                composability, competitive_density, timing_fit, compounding_value,
                overall_score, rank, strengths, weaknesses, recommendation, weights_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evaluation.buildable_unit_id,
                evaluation.pain_severity.model_dump_json(),
                evaluation.addressable_scale.model_dump_json(),
                evaluation.build_effort.model_dump_json(),
                evaluation.composability.model_dump_json(),
                evaluation.competitive_density.model_dump_json(),
                evaluation.timing_fit.model_dump_json(),
                evaluation.compounding_value.model_dump_json(),
                evaluation.overall_score,
                evaluation.rank,
                json.dumps(evaluation.strengths),
                json.dumps(evaluation.weaknesses),
                evaluation.recommendation,
                json.dumps(evaluation.weights_used),
            ),
        )
        self._commit()
        return evaluation

    def get_evaluation(self, unit_id: str) -> UtilityEvaluation | None:
        row = self.conn.execute(
            "SELECT * FROM evaluations WHERE buildable_unit_id = ?", (unit_id,)
        ).fetchone()
        return _row_to_evaluation(row) if row else None

    # ── Feedback ─────────────────────────────────────────────────────

    def insert_feedback(
        self,
        unit_id: str,
        outcome: str,
        reason: str = "",
        approval_score: int | None = None,
    ) -> None:
        """Record feedback on a buildable unit.

        outcome: approved | rejected | abandoned | synthesized
        approval_score: 1-10 conviction score (only for approvals)
        """
        # Get dimension values from evaluation if available
        evaluation = self.get_evaluation(unit_id)
        dimension_values = {}
        if evaluation:
            dimension_values = {
                "pain_severity": evaluation.pain_severity.value,
                "addressable_scale": evaluation.addressable_scale.value,
                "build_effort": evaluation.build_effort.value,
                "composability": evaluation.composability.value,
                "competitive_density": evaluation.competitive_density.value,
                "timing_fit": evaluation.timing_fit.value,
                "compounding_value": evaluation.compounding_value.value,
            }

        self.conn.execute(
            """INSERT INTO feedback
               (buildable_unit_id, outcome, reason, dimension_values, approval_score, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (unit_id, outcome, reason, json.dumps(dimension_values), approval_score, _now_iso()),
        )
        self._commit()

    def get_feedback_log(self, *, limit: int = 50) -> list[dict]:
        """Get recent feedback records with unit details for display."""
        rows = self.conn.execute(
            """SELECT f.buildable_unit_id, f.outcome, f.reason, f.approval_score,
                      f.created_at,
                      bu.title, bu.domain, bu.category,
                      e.overall_score, e.recommendation
               FROM feedback f
               JOIN buildable_units bu ON f.buildable_unit_id = bu.id
               LEFT JOIN evaluations e ON f.buildable_unit_id = e.buildable_unit_id
               ORDER BY f.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "unit_id": row["buildable_unit_id"],
                "outcome": row["outcome"],
                "reason": row["reason"],
                "approval_score": row["approval_score"],
                "created_at": row["created_at"],
                "title": row["title"],
                "domain": row["domain"],
                "category": row["category"],
                "score": row["overall_score"],
                "recommendation": row["recommendation"],
            }
            for row in rows
        ]

    def has_feedback(self, unit_id: str) -> bool:
        """Check if a buildable unit already has feedback."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE buildable_unit_id = ?",
            (unit_id,),
        ).fetchone()
        return row[0] > 0

    def get_feedback_outcomes(self) -> list[dict]:
        """Get all feedback records formatted for weight adaptation."""
        rows = self.conn.execute(
            "SELECT buildable_unit_id, outcome, dimension_values, approval_score FROM feedback"
        ).fetchall()

        outcomes = []
        for row in rows:
            dim_vals = json.loads(row["dimension_values"])
            success = row["outcome"] in ("approved", "published")
            outcomes.append({
                "buildable_unit_id": row["buildable_unit_id"],
                "dimension_values": dim_vals,
                "success": success,
                "approval_score": row["approval_score"],
            })
        return outcomes

    # ── Pipeline Runs ─────────────────────────────────────────────────

    def insert_pipeline_run(self, run_id: str, config: dict) -> None:
        """Record a new pipeline run."""
        self.conn.execute(
            "INSERT INTO pipeline_runs (id, started_at, config) VALUES (?, ?, ?)",
            (run_id, _now_iso(), json.dumps(config)),
        )
        self._commit()

    def update_pipeline_run(self, run_id: str, **metrics: object) -> None:
        """Update a pipeline run with completion metrics."""
        self.conn.execute(
            """UPDATE pipeline_runs SET
               completed_at = ?,
               signals_fetched = ?, signals_new = ?,
               insights_generated = ?, ideas_generated = ?,
               ideas_evaluated = ?,
               clusters_found = ?, gaps_detected = ?,
               avg_idea_score = ?,
               fetch_allocation = ?, token_usage = ?,
               adapter_metrics = ?
               WHERE id = ?""",
            (
                _now_iso(),
                metrics.get("signals_fetched", 0),
                metrics.get("signals_new", 0),
                metrics.get("insights_generated", 0),
                metrics.get("ideas_generated", 0),
                metrics.get("ideas_evaluated", 0),
                metrics.get("clusters_found", 0),
                metrics.get("gaps_detected", 0),
                metrics.get("avg_idea_score", 0.0),
                json.dumps(metrics.get("fetch_allocation", {})),
                json.dumps(metrics.get("token_usage", {})),
                json.dumps(metrics.get("adapter_metrics", {})),
                run_id,
            ),
        )
        self._commit()

    def get_pipeline_runs(self, *, limit: int = 20) -> list[dict]:
        """Get recent pipeline runs."""
        rows = self.conn.execute(
            """SELECT * FROM pipeline_runs WHERE archived_at IS NULL
               ORDER BY started_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "config": json.loads(row["config"]),
                "signals_fetched": row["signals_fetched"],
                "signals_new": row["signals_new"],
                "insights_generated": row["insights_generated"],
                "ideas_generated": row["ideas_generated"],
                "ideas_evaluated": row["ideas_evaluated"],
                "clusters_found": row["clusters_found"],
                "gaps_detected": row["gaps_detected"],
                "avg_idea_score": row["avg_idea_score"],
                "fetch_allocation": json.loads(row["fetch_allocation"]),
                "token_usage": json.loads(row["token_usage"]),
                "adapter_metrics": json.loads(row["adapter_metrics"]),
            }
            for row in rows
        ]

    # ── Pipeline Run Domains ────────────────────────────────────────────

    def insert_pipeline_run_domain(self, run_id: str, domain: str, stats: dict) -> None:
        """Record per-domain stats for a pipeline run."""
        row_id = _gen_id("prd")
        self.conn.execute(
            """INSERT INTO pipeline_run_domains
               (id, run_id, domain, signals_fetched, insights_generated,
                ideas_generated, ideas_evaluated, avg_score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row_id,
                run_id,
                domain,
                stats.get("signals_fetched", 0),
                stats.get("insights_generated", 0),
                stats.get("ideas_generated", 0),
                stats.get("ideas_evaluated", 0),
                stats.get("avg_score", 0.0),
                _now_iso(),
            ),
        )
        self._commit()

    def get_pipeline_run_domains(self, run_id: str) -> list[dict]:
        """Get all per-domain stats for a pipeline run."""
        rows = self.conn.execute(
            "SELECT * FROM pipeline_run_domains WHERE run_id = ? ORDER BY domain",
            (run_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "run_id": row["run_id"],
                "domain": row["domain"],
                "signals_fetched": row["signals_fetched"],
                "insights_generated": row["insights_generated"],
                "ideas_generated": row["ideas_generated"],
                "ideas_evaluated": row["ideas_evaluated"],
                "avg_score": row["avg_score"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_domain_performance(self, domain: str, *, limit: int = 10) -> list[dict]:
        """Get recent pipeline run stats for a specific domain (newest first)."""
        rows = self.conn.execute(
            """SELECT prd.*, pr.started_at as run_started_at
               FROM pipeline_run_domains prd
               JOIN pipeline_runs pr ON prd.run_id = pr.id
               WHERE prd.domain = ?
               ORDER BY pr.started_at DESC
               LIMIT ?""",
            (domain, limit),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "run_id": row["run_id"],
                "domain": row["domain"],
                "signals_fetched": row["signals_fetched"],
                "insights_generated": row["insights_generated"],
                "ideas_generated": row["ideas_generated"],
                "ideas_evaluated": row["ideas_evaluated"],
                "avg_score": row["avg_score"],
                "created_at": row["created_at"],
                "run_started_at": row["run_started_at"],
            }
            for row in rows
        ]

    # ── Attribution ───────────────────────────────────────────────────

    def get_feedback_with_attribution(self, *, limit: int = 100) -> list[dict]:
        """Get feedback records enriched with source attribution.

        Traces: feedback → buildable_unit → evidence_signals → signals.source_adapter.
        """
        rows = self.conn.execute(
            """SELECT f.buildable_unit_id, f.outcome, f.reason,
                      bu.evidence_signals, bu.category, bu.target_users
               FROM feedback f
               JOIN buildable_units bu ON f.buildable_unit_id = bu.id
               ORDER BY f.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()

        if not rows:
            return []

        # Collect all signal IDs across all feedback records
        all_signal_ids: set[str] = set()
        for row in rows:
            sig_ids = json.loads(row["evidence_signals"])
            all_signal_ids.update(sig_ids)

        # Batch-query signal → adapter mapping
        sig_to_adapter: dict[str, str] = {}
        if all_signal_ids:
            placeholders = ",".join("?" for _ in all_signal_ids)
            sig_rows = self.conn.execute(
                f"SELECT id, source_adapter FROM signals WHERE id IN ({placeholders})",
                list(all_signal_ids),
            ).fetchall()
            for sr in sig_rows:
                sig_to_adapter[sr["id"]] = sr["source_adapter"]

        results = []
        for row in rows:
            sig_ids = json.loads(row["evidence_signals"])
            adapters = list({sig_to_adapter[sid] for sid in sig_ids if sid in sig_to_adapter})
            evaluation = self.get_evaluation(row["buildable_unit_id"])
            results.append({
                "unit_id": row["buildable_unit_id"],
                "outcome": row["outcome"],
                "reason": row["reason"],
                "evidence_signal_ids": sig_ids,
                "source_adapters": adapters,
                "category": row["category"],
                "target_users": row["target_users"],
                "eval_score": evaluation.overall_score if evaluation else 0.0,
            })
        return results

    def get_adapter_approval_stats(self) -> dict[str, dict]:
        """Get per-adapter approval stats from feedback attribution.

        Returns dict[adapter_name, {total_feedbacked, approved, rejected, approval_rate}].
        """
        attributed = self.get_feedback_with_attribution(limit=500)
        if not attributed:
            return {}

        adapter_stats: dict[str, dict] = {}
        for record in attributed:
            is_approved = record["outcome"] in ("approved", "published")
            is_rejected = record["outcome"] in ("rejected", "abandoned")
            if not is_approved and not is_rejected:
                continue
            for adapter in record["source_adapters"]:
                if adapter not in adapter_stats:
                    adapter_stats[adapter] = {
                        "total_feedbacked": 0,
                        "approved": 0,
                        "rejected": 0,
                        "approval_rate": 0.0,
                    }
                adapter_stats[adapter]["total_feedbacked"] += 1
                if is_approved:
                    adapter_stats[adapter]["approved"] += 1
                else:
                    adapter_stats[adapter]["rejected"] += 1

        for stats in adapter_stats.values():
            total = stats["total_feedbacked"]
            stats["approval_rate"] = stats["approved"] / total if total > 0 else 0.0

        return adapter_stats

    # ── Data Retention ───────────────────────────────────────────────────

    def archive_old_records(self, days: int = 90) -> dict[str, int]:
        """Archive old records by setting archived_at timestamp.

        - Signals: Only if synthesized (synthesized_at IS NOT NULL) and older than `days`
        - Insights: Only if all referencing buildable_units are terminal (rejected/abandoned)
        - Pipeline runs: All older than `days`

        Returns counts of archived records per table.
        """
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        now = _now_iso()

        # Archive old synthesized signals
        cursor = self.conn.execute(
            """UPDATE signals
               SET archived_at = ?
               WHERE archived_at IS NULL
               AND synthesized_at IS NOT NULL
               AND fetched_at < ?""",
            (now, cutoff),
        )
        signals_archived = cursor.rowcount

        # Archive insights where all referencing buildable_units are terminal
        # First, get all insights that are old enough
        old_insights = self.conn.execute(
            """SELECT id, evidence FROM insights
               WHERE archived_at IS NULL AND created_at < ?""",
            (cutoff,),
        ).fetchall()

        # Check which have all terminal units
        archivable_insight_ids = []
        for row in old_insights:
            insight_id = row[0]

            # Find buildable_units that reference this insight
            units = self.conn.execute(
                """SELECT status FROM buildable_units
                   WHERE inspiring_insights LIKE ?""",
                (f'%"{insight_id}"%',),
            ).fetchall()

            # If no units reference it, or all are terminal, archive it
            if not units or all(u[0] in ("rejected", "abandoned") for u in units):
                archivable_insight_ids.append(insight_id)

        insights_archived = 0
        if archivable_insight_ids:
            placeholders = ",".join("?" for _ in archivable_insight_ids)
            self.conn.execute(
                f"UPDATE insights SET archived_at = ? WHERE id IN ({placeholders})",
                [now] + archivable_insight_ids,
            )
            insights_archived = len(archivable_insight_ids)

        # Archive old pipeline runs
        cursor = self.conn.execute(
            """UPDATE pipeline_runs
               SET archived_at = ?
               WHERE archived_at IS NULL
               AND started_at < ?""",
            (now, cutoff),
        )
        runs_archived = cursor.rowcount

        self._commit()

        return {
            "signals_archived": signals_archived,
            "insights_archived": insights_archived,
            "runs_archived": runs_archived,
        }

    def purge_archived(self, before_days: int = 180) -> dict[str, int]:
        """Permanently delete records archived more than `before_days` ago.

        Returns counts of deleted records per table.
        """
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(days=before_days)).isoformat()

        # Delete old archived signals
        cursor = self.conn.execute(
            """DELETE FROM signals
               WHERE archived_at IS NOT NULL
               AND archived_at < ?""",
            (cutoff,),
        )
        signals_deleted = cursor.rowcount

        # Delete old archived insights
        cursor = self.conn.execute(
            """DELETE FROM insights
               WHERE archived_at IS NOT NULL
               AND archived_at < ?""",
            (cutoff,),
        )
        insights_deleted = cursor.rowcount

        # Delete old archived pipeline runs
        cursor = self.conn.execute(
            """DELETE FROM pipeline_runs
               WHERE archived_at IS NOT NULL
               AND archived_at < ?""",
            (cutoff,),
        )
        runs_deleted = cursor.rowcount

        self._commit()

        return {
            "signals_deleted": signals_deleted,
            "insights_deleted": insights_deleted,
            "runs_deleted": runs_deleted,
        }

    def retention_stats(self) -> dict:
        """Get counts of total, active, and archived records per table."""
        stats = {}

        for table in ["signals", "insights", "pipeline_runs"]:
            total = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            active = self.conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE archived_at IS NULL"
            ).fetchone()[0]
            archived = self.conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE archived_at IS NOT NULL"
            ).fetchone()[0]
            stats[table] = {
                "total": total,
                "active": active,
                "archived": archived,
            }

        return stats


# ── Row conversion helpers ───────────────────────────────────────────


def _row_to_signal(row: sqlite3.Row) -> Signal:
    metadata = json.loads(row["metadata"])
    signal_role = row["signal_role"] if "signal_role" in row.keys() else ""
    if signal_role:
        metadata["signal_role"] = signal_role
    return Signal(
        id=row["id"],
        source_type=row["source_type"],
        source_adapter=row["source_adapter"],
        title=row["title"],
        content=row["content"],
        url=row["url"],
        author=row["author"],
        published_at=row["published_at"],
        fetched_at=row["fetched_at"],
        tags=json.loads(row["tags"]),
        credibility=row["credibility"],
        metadata=metadata,
    )


def _row_to_insight(row: sqlite3.Row) -> Insight:
    return Insight(
        id=row["id"],
        category=row["category"],
        title=row["title"],
        summary=row["summary"],
        evidence=json.loads(row["evidence"]),
        confidence=row["confidence"],
        domains=json.loads(row["domains"]),
        implications=json.loads(row["implications"]),
        time_horizon=row["time_horizon"],
        created_at=row["created_at"],
    )


def _row_to_buildable_unit(row: sqlite3.Row) -> BuildableUnit:
    return BuildableUnit(
        id=row["id"],
        title=row["title"],
        one_liner=row["one_liner"],
        category=row["category"],
        ideation_mode=row["ideation_mode"],
        problem=row["problem"],
        solution=row["solution"],
        target_users=row["target_users"],
        value_proposition=row["value_proposition"],
        specific_user=row["specific_user"] if "specific_user" in row.keys() else "",
        buyer=row["buyer"] if "buyer" in row.keys() else "",
        workflow_context=row["workflow_context"] if "workflow_context" in row.keys() else "",
        current_workaround=row["current_workaround"] if "current_workaround" in row.keys() else "",
        why_now=row["why_now"] if "why_now" in row.keys() else "",
        validation_plan=row["validation_plan"] if "validation_plan" in row.keys() else "",
        first_10_customers=row["first_10_customers"] if "first_10_customers" in row.keys() else "",
        domain_risks=json.loads(row["domain_risks"]) if "domain_risks" in row.keys() else [],
        evidence_rationale=row["evidence_rationale"] if "evidence_rationale" in row.keys() else "",
        novelty_score=row["novelty_score"] if "novelty_score" in row.keys() else 0.0,
        usefulness_score=row["usefulness_score"] if "usefulness_score" in row.keys() else 0.0,
        quality_score=row["quality_score"] if "quality_score" in row.keys() else 0.0,
        rejection_tags=json.loads(row["rejection_tags"]) if "rejection_tags" in row.keys() else [],
        inspiring_insights=json.loads(row["inspiring_insights"]),
        evidence_signals=json.loads(row["evidence_signals"]),
        tech_approach=row["tech_approach"],
        suggested_stack=json.loads(row["suggested_stack"]),
        composability_notes=row["composability_notes"],
        status=row["status"],
        domain=row["domain"] if "domain" in row.keys() else "",
        prior_art_status=row["prior_art_status"] if "prior_art_status" in row.keys() else "unchecked",
        source_idea_ids=json.loads(row["source_idea_ids"]) if "source_idea_ids" in row.keys() else [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_evaluation(row: sqlite3.Row) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=row["buildable_unit_id"],
        pain_severity=DimensionScore.model_validate_json(row["pain_severity"]),
        addressable_scale=DimensionScore.model_validate_json(row["addressable_scale"]),
        build_effort=DimensionScore.model_validate_json(row["build_effort"]),
        composability=DimensionScore.model_validate_json(row["composability"]),
        competitive_density=DimensionScore.model_validate_json(row["competitive_density"]),
        timing_fit=DimensionScore.model_validate_json(row["timing_fit"]),
        compounding_value=DimensionScore.model_validate_json(row["compounding_value"]),
        overall_score=row["overall_score"],
        rank=row["rank"],
        strengths=json.loads(row["strengths"]),
        weaknesses=json.loads(row["weaknesses"]),
        recommendation=row["recommendation"],
        weights_used=json.loads(row["weights_used"]),
    )
