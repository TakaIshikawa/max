"""Evaluation recommendation distribution export report."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.evaluation_recommendation_distribution_report.v1"
KIND = "max.evaluation_recommendation_distribution_report"
LABELS = ("approve", "reject", "revise")
_STATUS_ORDER = {"collapsed": 0, "skewed": 1, "balanced": 2}


def generate_evaluation_recommendation_distribution_report(evaluations: Iterable[dict[str, Any]], *, skew_threshold: float = 0.7, collapsed_threshold: float = 0.9) -> dict[str, Any]:
    groups: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for raw in evaluations:
        if not isinstance(raw, dict):
            continue
        key = (_text(raw.get("profile") or raw.get("profile_id")) or "default", _text(raw.get("model") or raw.get("model_name")) or "unknown-model")
        label = _label(raw.get("recommendation") or raw.get("label") or raw.get("outcome"))
        groups[key][label] += 1
    rows = []
    for (profile, model), counts in groups.items():
        total = sum(counts.values())
        percentages = {label: round(counts[label] / total * 100, 2) if total else 0.0 for label in LABELS}
        dominant = max(LABELS, key=lambda label: (counts[label], label))
        dominant_share = counts[dominant] / total if total else 0.0
        rows.append({"profile": profile, "model": model, "evaluation_count": total, "recommendation_counts": {label: counts[label] for label in LABELS}, "recommendation_percentages": percentages, "dominant_recommendation": dominant if total else None, "dominant_share": round(dominant_share, 4), "status": "collapsed" if dominant_share >= collapsed_threshold and total else ("skewed" if dominant_share >= skew_threshold and total else "balanced")})
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["profile"].casefold(), row["model"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": rows[0]["status"] if rows else "balanced", "group_count": len(rows), "evaluation_count": sum(row["evaluation_count"] for row in rows)}, "rows": rows}


def _label(value: Any) -> str:
    text = _text(value)
    return text if text in LABELS else "revise"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().lower().split()) if value is not None else ""
