"""Retrospective analysis — rule-based pattern extraction from feedback history."""

from __future__ import annotations

from dataclasses import dataclass, field

from max.store.db import Store


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
