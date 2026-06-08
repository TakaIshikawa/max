"""Evaluation rubric version export report."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.evaluation_rubric_version_report.v1"
KIND = "max.evaluation_rubric_version_report"
_STATUS_ORDER = {"stale": 0, "mixed": 1, "current": 2}


def generate_evaluation_rubric_version_report(records: Iterable[dict[str, Any]], *, current_version: str, stale_threshold: float = 0.5) -> dict[str, Any]:
    current = _text(current_version)
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    for raw in records:
        if isinstance(raw, dict):
            groups[_text(raw.get("profile") or raw.get("profile_id")) or "default"][_text(raw.get("rubric_version") or raw.get("version")) or "unknown"] += 1
    rows = []
    for profile, counts in groups.items():
        total = sum(counts.values())
        stale = total - counts[current]
        stale_pct = round(stale / total * 100, 2) if total else 0.0
        rows.append({"profile": profile, "evaluation_count": total, "current_version": current, "version_counts": dict(sorted(counts.items())), "stale_count": stale, "stale_percent": stale_pct, "status": "current" if stale == 0 else ("stale" if stale / total >= stale_threshold else "mixed")})
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["profile"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": rows[0]["status"] if rows else "current", "group_count": len(rows), "evaluation_count": sum(row["evaluation_count"] for row in rows), "stale_count": sum(row["stale_count"] for row in rows), "current_version": current}, "rows": rows}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
