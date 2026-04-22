"""Retrospective analysis — rule-based pattern extraction from feedback history."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from max.store.db import Store
from max.types.trends import TrendPoint


@dataclass
class RetrospectiveContext:
    """Learned patterns from feedback history."""

    successful_categories: list[str] = field(default_factory=list)
    failed_categories: list[str] = field(default_factory=list)
    successful_adapters: list[str] = field(default_factory=list)
    underperforming_adapters: list[str] = field(default_factory=list)
    preferred_target_users: str | None = None
    avg_approved_score: float = 0.0
    avg_rejected_score: float = 0.0
    pattern_count: int = 0


FeedbackTrendBucket = Literal["day", "week", "month"]


@dataclass
class FeedbackTrendDomainPoint:
    """Feedback metrics for one domain within a time window."""

    domain: str
    total_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    avg_score: float


@dataclass
class FeedbackTrendPoint:
    """Feedback metrics for a single time window."""

    window_start: datetime
    window_end: datetime
    total_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    avg_score: float
    domains: list[FeedbackTrendDomainPoint] = field(default_factory=list)


@dataclass
class FeedbackTrendSummary:
    """Time-windowed feedback trend metrics."""

    days: int
    bucket: FeedbackTrendBucket
    window_count: int
    total_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    avg_score: float
    windows: list[FeedbackTrendPoint] = field(default_factory=list)


@dataclass
class PipelineThroughputTrendPoint:
    """Pipeline execution metrics for a single time window."""

    window_start: datetime
    window_end: datetime
    run_count: int
    completed_count: int
    failed_count: int
    signals_fetched: int
    signals_new: int
    insights_generated: int
    ideas_generated: int
    ideas_evaluated: int
    estimated_cost_usd: float
    avg_idea_score: float


@dataclass
class PipelineThroughputTrendSummary:
    """Time-windowed pipeline execution throughput metrics."""

    days: int
    bucket: FeedbackTrendBucket
    window_count: int
    run_count: int
    completed_count: int
    failed_count: int
    signals_fetched: int
    signals_new: int
    insights_generated: int
    ideas_generated: int
    ideas_evaluated: int
    estimated_cost_usd: float
    avg_idea_score: float
    windows: list[PipelineThroughputTrendPoint] = field(default_factory=list)


def _bucket_delta(bucket: FeedbackTrendBucket) -> timedelta:
    if bucket == "day":
        return timedelta(days=1)
    if bucket == "week":
        return timedelta(days=7)
    if bucket == "month":
        return timedelta(days=30)
    raise ValueError("bucket must be one of: day, week, month")


def _feedback_metrics(rows: list[dict]) -> tuple[int, int, int, float, float]:
    total = len(rows)
    approved = sum(1 for row in rows if row["outcome"] in ("approved", "published"))
    rejected = sum(1 for row in rows if row["outcome"] in ("rejected", "abandoned"))
    approval_rate = approved / total if total else 0.0
    scores = [row["overall_score"] for row in rows if row["overall_score"] is not None]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    return total, approved, rejected, approval_rate, avg_score


def _pipeline_run_cost(row: dict) -> float:
    from max import config
    from max.llm.client import estimate_token_cost_usd, token_counts_from_usage

    token_usage = row.get("token_usage") or {}
    stored_cost = token_usage.get("estimated_cost_usd")
    if isinstance(stored_cost, (int, float)):
        return float(stored_cost)

    input_tokens, output_tokens = token_counts_from_usage(token_usage)
    model = str((row.get("config") or {}).get("model") or config.MODEL)
    return estimate_token_cost_usd(input_tokens, output_tokens, model=model)


def _pipeline_metrics(rows: list[dict]) -> tuple[int, int, int, int, int, int, int, int, float, float]:
    run_count = len(rows)
    completed_count = sum(1 for row in rows if row["status"] == "completed")
    failed_count = sum(1 for row in rows if row["status"] == "failed")
    signals_fetched = sum(row["signals_fetched"] for row in rows)
    signals_new = sum(row["signals_new"] for row in rows)
    insights_generated = sum(row["insights_generated"] for row in rows)
    ideas_generated = sum(row["ideas_generated"] for row in rows)
    ideas_evaluated = sum(row["ideas_evaluated"] for row in rows)
    estimated_cost_usd = sum(_pipeline_run_cost(row) for row in rows)
    scores = [row["avg_idea_score"] for row in rows if row["avg_idea_score"] > 0]
    avg_idea_score = sum(scores) / len(scores) if scores else 0.0
    return (
        run_count,
        completed_count,
        failed_count,
        signals_fetched,
        signals_new,
        insights_generated,
        ideas_generated,
        ideas_evaluated,
        estimated_cost_usd,
        avg_idea_score,
    )


def detect_pipeline_trends(
    store: Store,
    *,
    days: int = 30,
    bucket: FeedbackTrendBucket = "day",
    now: datetime | None = None,
) -> PipelineThroughputTrendSummary:
    """Compute pipeline execution throughput across rolling time windows.

    Buckets cover the last *days* days, include empty windows, and exclude
    archived pipeline runs.
    """
    if days < 1:
        raise ValueError("days must be at least 1")

    delta = _bucket_delta(bucket)
    end = now or datetime.now(UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    start = end - timedelta(days=days)

    rows = store.conn.execute(
        """SELECT *
           FROM pipeline_runs
           WHERE archived_at IS NULL
             AND started_at >= ? AND started_at <= ?
           ORDER BY started_at ASC""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    run_rows = [dict(row) for row in rows]

    import json

    for row in run_rows:
        row["config"] = json.loads(row["config"] or "{}")
        row["token_usage"] = json.loads(row["token_usage"] or "{}")

    windows: list[PipelineThroughputTrendPoint] = []
    window_start = start
    while window_start < end:
        window_end = min(window_start + delta, end)
        bucket_rows = [
            row for row in run_rows
            if window_start.isoformat() <= row["started_at"] < window_end.isoformat()
        ]
        (
            run_count,
            completed_count,
            failed_count,
            signals_fetched,
            signals_new,
            insights_generated,
            ideas_generated,
            ideas_evaluated,
            estimated_cost_usd,
            avg_idea_score,
        ) = _pipeline_metrics(bucket_rows)

        windows.append(
            PipelineThroughputTrendPoint(
                window_start=window_start,
                window_end=window_end,
                run_count=run_count,
                completed_count=completed_count,
                failed_count=failed_count,
                signals_fetched=signals_fetched,
                signals_new=signals_new,
                insights_generated=insights_generated,
                ideas_generated=ideas_generated,
                ideas_evaluated=ideas_evaluated,
                estimated_cost_usd=estimated_cost_usd,
                avg_idea_score=avg_idea_score,
            )
        )
        window_start = window_end

    (
        run_count,
        completed_count,
        failed_count,
        signals_fetched,
        signals_new,
        insights_generated,
        ideas_generated,
        ideas_evaluated,
        estimated_cost_usd,
        avg_idea_score,
    ) = _pipeline_metrics(run_rows)
    return PipelineThroughputTrendSummary(
        days=days,
        bucket=bucket,
        window_count=len(windows),
        run_count=run_count,
        completed_count=completed_count,
        failed_count=failed_count,
        signals_fetched=signals_fetched,
        signals_new=signals_new,
        insights_generated=insights_generated,
        ideas_generated=ideas_generated,
        ideas_evaluated=ideas_evaluated,
        estimated_cost_usd=estimated_cost_usd,
        avg_idea_score=avg_idea_score,
        windows=windows,
    )


def detect_feedback_trends(
    store: Store,
    *,
    days: int = 30,
    bucket: FeedbackTrendBucket = "day",
    now: datetime | None = None,
) -> FeedbackTrendSummary:
    """Compute feedback metrics across rolling time windows.

    Buckets cover the last *days* days, include empty windows, and use
    evaluation overall scores for score averages.
    """
    if days < 1:
        raise ValueError("days must be at least 1")

    delta = _bucket_delta(bucket)
    end = now or datetime.now(UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    start = end - timedelta(days=days)

    rows = store.conn.execute(
        """SELECT f.outcome, f.created_at,
                  COALESCE(NULLIF(bu.domain, ''), 'unassigned') AS domain,
                  e.overall_score
           FROM feedback f
           JOIN buildable_units bu ON f.buildable_unit_id = bu.id
           LEFT JOIN evaluations e
             ON f.buildable_unit_id = e.buildable_unit_id
           WHERE f.created_at >= ? AND f.created_at <= ?
           ORDER BY f.created_at ASC""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    feedback_rows = [dict(row) for row in rows]

    windows: list[FeedbackTrendPoint] = []
    window_start = start
    while window_start < end:
        window_end = min(window_start + delta, end)
        bucket_rows = [
            row for row in feedback_rows
            if window_start.isoformat() <= row["created_at"] < window_end.isoformat()
        ]
        total, approved, rejected, approval_rate, avg_score = _feedback_metrics(bucket_rows)

        domain_points: list[FeedbackTrendDomainPoint] = []
        for domain in sorted({row["domain"] for row in bucket_rows}):
            domain_rows = [row for row in bucket_rows if row["domain"] == domain]
            (
                domain_total,
                domain_approved,
                domain_rejected,
                domain_approval_rate,
                domain_avg_score,
            ) = _feedback_metrics(domain_rows)
            domain_points.append(
                FeedbackTrendDomainPoint(
                    domain=domain,
                    total_count=domain_total,
                    approved_count=domain_approved,
                    rejected_count=domain_rejected,
                    approval_rate=domain_approval_rate,
                    avg_score=domain_avg_score,
                )
            )

        windows.append(
            FeedbackTrendPoint(
                window_start=window_start,
                window_end=window_end,
                total_count=total,
                approved_count=approved,
                rejected_count=rejected,
                approval_rate=approval_rate,
                avg_score=avg_score,
                domains=domain_points,
            )
        )
        window_start = window_end

    total, approved, rejected, approval_rate, avg_score = _feedback_metrics(feedback_rows)
    return FeedbackTrendSummary(
        days=days,
        bucket=bucket,
        window_count=len(windows),
        total_count=total,
        approved_count=approved,
        rejected_count=rejected,
        approval_rate=approval_rate,
        avg_score=avg_score,
        windows=windows,
    )


def analyze_retrospective(
    store: Store,
    *,
    min_outcomes: int = 4,
) -> RetrospectiveContext | None:
    """Analyze feedback history to extract patterns.

    Returns None when insufficient data (< min_outcomes or no diversity).
    """
    attributed = store.get_feedback_with_attribution()
    if len(attributed) < min_outcomes:
        return None

    approved = [r for r in attributed if r["outcome"] in ("approved", "published")]
    rejected = [r for r in attributed if r["outcome"] in ("rejected", "abandoned")]

    if not approved or not rejected:
        return None

    ctx = RetrospectiveContext(pattern_count=len(attributed))

    # Category analysis
    cat_stats: dict[str, dict[str, int]] = {}
    for record in attributed:
        cat = record["category"]
        if cat not in cat_stats:
            cat_stats[cat] = {"approved": 0, "total": 0}
        cat_stats[cat]["total"] += 1
        if record["outcome"] in ("approved", "published"):
            cat_stats[cat]["approved"] += 1

    for cat, stats in cat_stats.items():
        rate = stats["approved"] / stats["total"]
        if rate > 0.5:
            ctx.successful_categories.append(cat)
        elif rate < 0.3:
            ctx.failed_categories.append(cat)

    # Adapter analysis
    adapter_stats: dict[str, dict[str, int]] = {}
    for record in attributed:
        is_approved = record["outcome"] in ("approved", "published")
        for adapter in record["source_adapters"]:
            if adapter not in adapter_stats:
                adapter_stats[adapter] = {"approved": 0, "total": 0}
            adapter_stats[adapter]["total"] += 1
            if is_approved:
                adapter_stats[adapter]["approved"] += 1

    for adapter, stats in adapter_stats.items():
        rate = stats["approved"] / stats["total"]
        if rate > 0.5:
            ctx.successful_adapters.append(adapter)
        elif rate < 0.3:
            ctx.underperforming_adapters.append(adapter)

    # Target users analysis
    tu_stats: dict[str, dict[str, int]] = {}
    for record in attributed:
        tu = record["target_users"]
        if tu not in tu_stats:
            tu_stats[tu] = {"approved": 0, "total": 0}
        tu_stats[tu]["total"] += 1
        if record["outcome"] in ("approved", "published"):
            tu_stats[tu]["approved"] += 1

    if tu_stats:
        best_tu = max(
            tu_stats.items(),
            key=lambda x: x[1]["approved"] / x[1]["total"],
        )
        ctx.preferred_target_users = best_tu[0]

    # Score calibration
    approved_scores = [r["eval_score"] for r in approved if r["eval_score"] > 0]
    rejected_scores = [r["eval_score"] for r in rejected if r["eval_score"] > 0]

    if approved_scores:
        ctx.avg_approved_score = sum(approved_scores) / len(approved_scores)
    if rejected_scores:
        ctx.avg_rejected_score = sum(rejected_scores) / len(rejected_scores)

    return ctx


def format_retrospective_for_ideation(
    ctx: RetrospectiveContext | None,
) -> str | None:
    """Format retrospective patterns for injection into ideation prompts."""
    if ctx is None:
        return None

    lines = [f"HISTORICAL PATTERNS (from {ctx.pattern_count} feedback outcomes):"]

    if ctx.successful_categories:
        lines.append(f"- Categories that work well: {', '.join(ctx.successful_categories)}")
    if ctx.failed_categories:
        lines.append(f"- Categories that underperform: {', '.join(ctx.failed_categories)}")
    if ctx.successful_adapters:
        lines.append(f"- Best source adapters: {', '.join(ctx.successful_adapters)}")
    if ctx.underperforming_adapters:
        lines.append(
            f"- Underperforming adapters: {', '.join(ctx.underperforming_adapters)}"
        )
    if ctx.preferred_target_users:
        lines.append(f"- Preferred target users: {ctx.preferred_target_users}")
    if ctx.avg_approved_score > 0 and ctx.avg_rejected_score > 0:
        lines.append(
            f"- Score calibration: approved ideas avg {ctx.avg_approved_score:.1f}"
            f" vs rejected avg {ctx.avg_rejected_score:.1f}"
        )

    lines.append("")
    lines.append(
        "Prioritize idea types and patterns that align with historically successful outcomes."
    )
    lines.append(
        "Avoid patterns associated with rejected ideas unless the evidence is compelling."
    )

    return "\n".join(lines)


def detect_trends(
    store: Store,
    *,
    window: int = 5,
) -> list[TrendPoint]:
    """Detect approval rate trends over sliding windows of pipeline runs.

    Groups pipeline runs into windows of *window* runs each and computes
    per-window metrics from feedback recorded during each window's time range.

    Returns an empty list when there are fewer runs than *window*.
    """
    runs = store.get_pipeline_runs(limit=1000)
    if len(runs) < window:
        return []

    # Runs come newest-first; reverse to chronological order.
    runs = list(reversed(runs))

    points: list[TrendPoint] = []
    prev_rate: float | None = None

    for i in range(0, len(runs) - window + 1, window):
        chunk = runs[i : i + window]
        window_start = datetime.fromisoformat(chunk[0]["started_at"])
        window_end = datetime.fromisoformat(
            chunk[-1]["completed_at"] or chunk[-1]["started_at"]
        )

        # Query feedback recorded within this window's time range.
        rows = store.conn.execute(
            """SELECT f.outcome, e.overall_score
               FROM feedback f
               LEFT JOIN evaluations e
                 ON f.buildable_unit_id = e.buildable_unit_id
               WHERE f.created_at >= ? AND f.created_at <= ?""",
            (chunk[0]["started_at"], chunk[-1]["completed_at"] or chunk[-1]["started_at"]),
        ).fetchall()

        total = len(rows)
        if total == 0:
            approval_rate = 0.0
            avg_score = 0.0
        else:
            approved = sum(
                1 for r in rows if r["outcome"] in ("approved", "published")
            )
            approval_rate = approved / total
            scores = [r["overall_score"] for r in rows if r["overall_score"]]
            avg_score = sum(scores) / len(scores) if scores else 0.0

        signal_count = sum(c["signals_fetched"] for c in chunk)

        # Determine trend direction.
        if prev_rate is None:
            direction: str = "stable"
        else:
            delta = approval_rate - prev_rate
            if delta > 0.05:
                direction = "improving"
            elif delta < -0.05:
                direction = "declining"
            else:
                direction = "stable"

        points.append(
            TrendPoint(
                window_start=window_start,
                window_end=window_end,
                approval_rate=approval_rate,
                avg_score=avg_score,
                signal_count=signal_count,
                trend_direction=direction,
            )
        )
        prev_rate = approval_rate

    return points
