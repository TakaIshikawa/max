"""Evaluation gate escape export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.evaluation_gate_escape_report.v1"
KIND = "max.evaluation_gate_escape_report"
NEGATIVE_OUTCOMES = {"negative", "failed", "failure", "rejected", "churned", "lost", "bad", "poor"}
POSITIVE_OUTCOMES = {"positive", "passed", "success", "accepted", "won", "good"}


def generate_evaluation_gate_escape_report(
    evaluations: Iterable[dict[str, Any]],
    outcomes: Iterable[dict[str, Any]],
    *,
    score_floor: float = 0.7,
) -> dict[str, Any]:
    floor = _float(score_floor)
    outcome_by_idea = {_idea_id(raw): raw for raw in outcomes if _idea_id(raw)}
    dimension_totals: dict[str, dict[str, Any]] = defaultdict(lambda: {"passed": 0, "with_outcome": 0, "negative": 0, "ideas": set()})
    escaped_ideas: dict[str, dict[str, Any]] = {}
    total_passed = 0
    passed_with_outcome = 0
    negative_outcomes = 0

    for raw in evaluations:
        idea_id = _idea_id(raw) or "unknown-idea"
        score = _float(raw.get("score") or raw.get("evaluation_score") or raw.get("gate_score"))
        passed = _bool(raw.get("passed") or raw.get("gate_passed") or raw.get("approved")) or score >= floor
        if not passed:
            continue

        total_passed += 1
        dimension = _text(raw.get("dimension") or raw.get("evaluation_dimension") or raw.get("gate")) or "unknown-dimension"
        bucket = dimension_totals[dimension]
        bucket["passed"] += 1

        outcome = outcome_by_idea.get(idea_id)
        if not outcome:
            continue

        passed_with_outcome += 1
        bucket["with_outcome"] += 1
        negative = _is_negative_outcome(outcome)
        if negative:
            negative_outcomes += 1
            bucket["negative"] += 1
            bucket["ideas"].add(idea_id)
            escaped_ideas.setdefault(
                idea_id,
                {
                    "idea_id": idea_id,
                    "outcome": _outcome_label(outcome),
                    "dimensions": [],
                },
            )["dimensions"].append(dimension)

    dimensions = []
    for dimension, totals in dimension_totals.items():
        with_outcome = totals["with_outcome"]
        dimensions.append(
            {
                "dimension": dimension,
                "total_passed": totals["passed"],
                "passed_with_outcome": with_outcome,
                "negative_outcomes": totals["negative"],
                "escape_rate": _rate(totals["negative"], with_outcome),
                "escaped_ideas": sorted(totals["ideas"]),
            }
        )
    dimensions.sort(key=lambda row: (-row["escape_rate"], row["dimension"].casefold()))

    escapes = list(escaped_ideas.values())
    for row in escapes:
        row["dimensions"] = sorted(set(row["dimensions"]), key=str.casefold)
    escapes.sort(key=lambda row: row["idea_id"].casefold())

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "total_passed": total_passed,
            "passed_with_outcome": passed_with_outcome,
            "negative_outcomes": negative_outcomes,
            "escape_rate": _rate(negative_outcomes, passed_with_outcome),
            "score_floor": floor,
        },
        "dimensions": dimensions,
        "escapes": escapes,
    }


def _idea_id(raw: dict[str, Any]) -> str:
    return _text(raw.get("idea_id") or raw.get("id") or raw.get("unit_id"))


def _is_negative_outcome(raw: dict[str, Any]) -> bool:
    if isinstance(raw.get("negative"), bool):
        return bool(raw["negative"])
    if isinstance(raw.get("successful"), bool):
        return not bool(raw["successful"])
    label = _outcome_label(raw).lower()
    if label in NEGATIVE_OUTCOMES:
        return True
    if label in POSITIVE_OUTCOMES:
        return False
    return _float(raw.get("score") or raw.get("outcome_score")) < 0.5


def _outcome_label(raw: dict[str, Any]) -> str:
    return _text(raw.get("outcome") or raw.get("status") or raw.get("result")) or "unknown"


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "passed", "approved"}


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
