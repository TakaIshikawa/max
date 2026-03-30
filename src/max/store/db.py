"""SQLite Store — CRUD for all max entities."""

from __future__ import annotations

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
from max.types.tact_spec import TactSpec


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Store:
    """Single-connection SQLite store for max entities."""

    def __init__(self, db_path: str = DB_PATH, *, wal_mode: bool = False):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        if wal_mode:
            self.conn.execute("PRAGMA journal_mode=WAL")
        ensure_schema(self.conn)

    def close(self) -> None:
        self.conn.close()

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
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass  # duplicate URL — skip
        return signal

    def get_signals(self, *, limit: int = 100, source_type: str | None = None) -> list[Signal]:
        query = "SELECT * FROM signals"
        params: list = []
        if source_type:
            query += " WHERE source_type = ?"
            params.append(source_type)
        query += " ORDER BY fetched_at DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_signal(row) for row in rows]

    def count_signals(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]

    def get_unsynthesized_signals(self, *, limit: int = 100) -> list[Signal]:
        """Get signals that have not yet been synthesized."""
        rows = self.conn.execute(
            "SELECT * FROM signals WHERE synthesized_at IS NULL ORDER BY fetched_at DESC LIMIT ?",
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
        self.conn.commit()

    def get_signal(self, signal_id: str) -> Signal | None:
        """Get a single signal by ID."""
        row = self.conn.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()
        return _row_to_signal(row) if row else None

    def get_signals_by_role(self, role: str, *, limit: int = 100) -> list[Signal]:
        """Get signals filtered by signal_role."""
        rows = self.conn.execute(
            "SELECT * FROM signals WHERE signal_role = ? ORDER BY fetched_at DESC LIMIT ?",
            (role, limit),
        ).fetchall()
        return [_row_to_signal(row) for row in rows]

    def get_adapter_quality_stats(self) -> dict[str, dict]:
        """Get per-adapter signal utilization stats.

        Returns dict[adapter_name, {total_signals, insight_hit_rate, idea_hit_rate}].
        """
        rows = self.conn.execute(
            "SELECT source_adapter, COUNT(*) as cnt FROM signals GROUP BY source_adapter"
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
        self.conn.commit()
        return insight

    def get_insights(self, *, limit: int = 100) -> list[Insight]:
        rows = self.conn.execute(
            "SELECT * FROM insights ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_insight(row) for row in rows]

    def get_insight(self, insight_id: str) -> Insight | None:
        """Get a single insight by ID."""
        row = self.conn.execute(
            "SELECT * FROM insights WHERE id = ?", (insight_id,)
        ).fetchone()
        return _row_to_insight(row) if row else None

    # ── BuildableUnits ───────────────────────────────────────────────

    def insert_buildable_unit(self, unit: BuildableUnit) -> BuildableUnit:
        if not unit.id:
            unit.id = _gen_id("bu")
        self.conn.execute(
            """INSERT INTO buildable_units
               (id, title, one_liner, category, ideation_mode, problem, solution,
                target_users, value_proposition, inspiring_insights, evidence_signals,
                tech_approach, suggested_stack, composability_notes, status,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                unit.id,
                unit.title,
                unit.one_liner,
                unit.category.value,
                unit.ideation_mode.value,
                unit.problem,
                unit.solution,
                unit.target_users,
                unit.value_proposition,
                json.dumps(unit.inspiring_insights),
                json.dumps(unit.evidence_signals),
                unit.tech_approach,
                json.dumps(unit.suggested_stack),
                unit.composability_notes,
                unit.status,
                unit.created_at.isoformat(),
                unit.updated_at.isoformat(),
            ),
        )
        self.conn.commit()
        return unit

    def get_buildable_unit(self, unit_id: str) -> BuildableUnit | None:
        row = self.conn.execute(
            "SELECT * FROM buildable_units WHERE id = ?", (unit_id,)
        ).fetchone()
        return _row_to_buildable_unit(row) if row else None

    def get_buildable_units(
        self, *, limit: int = 100, status: str | None = None
    ) -> list[BuildableUnit]:
        query = "SELECT * FROM buildable_units"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_buildable_unit(row) for row in rows]

    def update_buildable_unit_status(self, unit_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE buildable_units SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now_iso(), unit_id),
        )
        self.conn.commit()

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
        self.conn.commit()
        return evaluation

    def get_evaluation(self, unit_id: str) -> UtilityEvaluation | None:
        row = self.conn.execute(
            "SELECT * FROM evaluations WHERE buildable_unit_id = ?", (unit_id,)
        ).fetchone()
        return _row_to_evaluation(row) if row else None

    # ── TactSpecs ────────────────────────────────────────────────────

    def insert_tact_spec(self, spec: TactSpec) -> TactSpec:
        self.conn.execute(
            """INSERT OR REPLACE INTO tact_specs
               (buildable_unit_id, spec_json, created_at)
               VALUES (?, ?, ?)""",
            (
                spec.buildable_unit_id,
                spec.model_dump_json(),
                _now_iso(),
            ),
        )
        self.conn.commit()
        return spec

    def get_tact_spec(self, unit_id: str) -> TactSpec | None:
        row = self.conn.execute(
            "SELECT * FROM tact_specs WHERE buildable_unit_id = ?", (unit_id,)
        ).fetchone()
        if not row:
            return None
        return TactSpec.model_validate_json(row["spec_json"])

    # ── Feedback ─────────────────────────────────────────────────────

    def insert_feedback(
        self,
        unit_id: str,
        outcome: str,
        reason: str = "",
    ) -> None:
        """Record feedback on a buildable unit.

        outcome: approved | rejected | published | abandoned
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
               (buildable_unit_id, outcome, reason, dimension_values, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (unit_id, outcome, reason, json.dumps(dimension_values), _now_iso()),
        )
        self.conn.commit()

    def get_feedback_outcomes(self) -> list[dict]:
        """Get all feedback records formatted for weight adaptation."""
        rows = self.conn.execute(
            "SELECT buildable_unit_id, outcome, dimension_values FROM feedback"
        ).fetchall()

        outcomes = []
        for row in rows:
            dim_vals = json.loads(row["dimension_values"])
            success = row["outcome"] in ("approved", "published")
            outcomes.append({
                "buildable_unit_id": row["buildable_unit_id"],
                "dimension_values": dim_vals,
                "success": success,
            })
        return outcomes


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
        inspiring_insights=json.loads(row["inspiring_insights"]),
        evidence_signals=json.loads(row["evidence_signals"]),
        tech_approach=row["tech_approach"],
        suggested_stack=json.loads(row["suggested_stack"]),
        composability_notes=row["composability_notes"],
        status=row["status"],
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
