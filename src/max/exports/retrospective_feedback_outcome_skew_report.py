"""Retrospective feedback outcome skew export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.retrospective_feedback_outcome_skew_report.v1"
KIND = "max.retrospective_feedback_outcome_skew_report"
OUTCOMES = ("approved", "rejected", "needs_revision", "unknown")


def generate_retrospective_feedback_outcome_skew_report(records: Iterable[dict[str, Any]], *, dimensions: Iterable[str] = ("profile", "category", "source"), minimum_sample: int = 3, skew_threshold: float = 0.8) -> dict[str, Any]:
    dims = [_text(dim) for dim in dimensions if _text(dim)]
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    total = 0
    for raw in records:
        total += 1
        outcome = _text(raw.get("outcome")).lower()
        outcome = outcome if outcome in OUTCOMES else "unknown"
        for dim in dims:
            value = _text(raw.get(dim)) or f"unknown-{dim}"
            row = groups.setdefault((dim, value), {"dimension": dim, "segment": value, "approved": 0, "rejected": 0, "needs_revision": 0, "unknown": 0, "total": 0})
            row[outcome] += 1
            row["total"] += 1
    distributions = sorted(groups.values(), key=lambda row: (row["dimension"], row["segment"].lower()))
    findings = []
    for row in distributions:
        approval_share = _rate(row["approved"], row["total"])
        rejection_share = _rate(row["rejected"], row["total"])
        if row["total"] >= minimum_sample and (approval_share >= skew_threshold or rejection_share >= skew_threshold):
            findings.append({**row, "approval_share": approval_share, "rejection_share": rejection_share, "skew_type": "approval" if approval_share >= rejection_share else "rejection", "recommendation": "Review feedback calibration and sample composition for this segment."})
    findings.sort(key=lambda row: (-max(row["approval_share"], row["rejection_share"]), row["dimension"], row["segment"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_feedback": total, "dimensions_analyzed": dims, "flagged_segments": len(findings), "minimum_sample": minimum_sample, "skew_threshold": skew_threshold}, "distributions": distributions, "findings": findings}


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

