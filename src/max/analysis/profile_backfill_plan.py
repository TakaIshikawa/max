"""Prioritized profile category backfill plan."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping


SCHEMA_VERSION = "max.profile_backfill_plan.v1"
KIND = "max.profile_backfill_plan"


def build_profile_backfill_plan(
    required_categories: list[Mapping[str, Any]],
    observed_coverage: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare required profile categories with observed coverage and prioritize backfill gaps."""

    observed = _observed_counts(observed_coverage)
    rows = []
    for index, requirement in enumerate(required_categories):
        profile = _clean(requirement.get("profile") or requirement.get("profile_id") or "default")
        category = _clean(requirement.get("category") or requirement.get("profile_category") or f"category-{index + 1}")
        target = _nonnegative_int(requirement.get("target_count", requirement.get("required_count", 1)))
        sources = [_clean(value) for value in _values(requirement.get("suggested_sources", requirement.get("sources", []))) if _clean(value)]
        current = observed.get((profile, category), 0)
        if current < target:
            rows.append(_backfill_row(profile, category, current, target, sources))

    rows.sort(key=lambda row: (_priority_order(row["priority"]), -int(row["gap_size"]), row["profile"], row["category"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "required_category_count": len(required_categories),
            "backfill_count": len(rows),
            "critical_count": sum(1 for row in rows if row["priority"] == "critical"),
            "moderate_count": sum(1 for row in rows if row["priority"] == "moderate"),
        },
        "backfill_rows": rows,
    }


def render_profile_backfill_plan_markdown(plan: Mapping[str, Any]) -> str:
    """Render a profile backfill plan as deterministic Markdown."""

    summary = plan["summary"]
    rows = list(plan.get("backfill_rows", []))
    lines = [
        "# Profile Backfill Plan",
        "",
        f"Schema: `{plan['schema_version']}`",
        f"Required categories: {summary['required_category_count']}",
        f"Backfill items: {summary['backfill_count']}",
        "",
        "## Critical Gaps",
        "",
    ]

    critical = [row for row in rows if row["priority"] == "critical"]
    moderate = [row for row in rows if row["priority"] == "moderate"]
    if critical:
        for row in critical:
            lines.append(_gap_line(row))
    else:
        lines.append("- No critical gaps.")

    lines.extend(["", "## Moderate Gaps", ""])
    if moderate:
        for row in moderate:
            lines.append(_gap_line(row))
    else:
        lines.append("- No moderate gaps.")

    lines.extend(["", "## Backfill Detail", ""])
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"### {row['profile']} / {row['category']}",
                    "",
                    f"- Current count: {row['current_count']}",
                    f"- Target count: {row['target_count']}",
                    f"- Gap size: {row['gap_size']}",
                    f"- Suggested sources: {', '.join(row['suggested_sources'])}",
                    f"- Priority: {row['priority']}",
                    "",
                ]
            )
    else:
        lines.append("All required profile categories meet target coverage.")

    return "\n".join(lines).rstrip() + "\n"


def _observed_counts(observed_coverage: list[Mapping[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for record in observed_coverage:
        profile = _clean(record.get("profile") or record.get("profile_id") or "default")
        category = _clean(record.get("category") or record.get("profile_category"))
        if not category:
            continue
        counts[(profile, category)] += _nonnegative_int(record.get("count", record.get("coverage_count", 1)))
    return counts


def _backfill_row(profile: str, category: str, current: int, target: int, sources: list[str]) -> dict[str, Any]:
    gap = max(0, target - current)
    priority = "critical" if current == 0 or gap / max(1, target) >= 0.5 else "moderate"
    return {
        "profile": profile,
        "category": category,
        "current_count": current,
        "target_count": target,
        "gap_size": gap,
        "suggested_sources": sources or ["customer_interviews", "support_tickets"],
        "priority": priority,
        "recommendation": _recommendation(priority, profile, category, gap),
    }


def _recommendation(priority: str, profile: str, category: str, gap: int) -> str:
    if priority == "critical":
        return f"backfill {gap} evidence item(s) for {profile} {category} before the next scoring run"
    return f"add {gap} evidence item(s) for {profile} {category} during the next enrichment cycle"


def _gap_line(row: Mapping[str, Any]) -> str:
    sources = ", ".join(row["suggested_sources"])
    return (
        f"- {row['profile']} / {row['category']}: current {row['current_count']}, "
        f"target {row['target_count']}, gap {row['gap_size']}; sources: {sources}"
    )


def _priority_order(priority: str) -> int:
    return {"critical": 0, "moderate": 1}.get(priority, 2)


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _nonnegative_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, number)


def _clean(value: Any) -> str:
    return str(value or "").strip()
