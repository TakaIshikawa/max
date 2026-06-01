"""Generate deterministic evaluation label dispute resolution plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.evaluation_label_dispute_plan.v1"
KIND = "max.spec.evaluation_label_dispute_plan"


def generate_evaluation_label_dispute_plan(disputes: Any, reviewers: Any, *, quorum: int = 2) -> dict[str, Any]:
    if quorum < 1:
        raise ValueError("quorum must be at least 1")
    ctx = context({})
    reviewer_rows = _reviewers(reviewers)
    dispute_rows = _disputes(disputes)
    assignments = _assignments(dispute_rows, reviewer_rows, quorum)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, dispute_count=len(dispute_rows), reviewer_count=len(reviewer_rows), quorum=quorum),
        "dimension_groups": _dimension_groups(dispute_rows),
        "reviewer_assignments": assignments,
        "evidence_packets": _evidence_packets(dispute_rows),
        "quorum_rules": _quorum_rules(quorum),
        "tie_break_handling": _tie_break_handling(),
        "audit_trail": _audit_trail(),
        "evidence_references": ctx["evidence_references"],
    }


def _disputes(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": compact(item.get("dispute_id") or item.get("id")) or f"dispute_{index}",
                "evaluation_id": compact(item.get("evaluation_id")) or "evaluation",
                "dimension": compact(item.get("dimension")) or "overall",
                "current_label": compact(item.get("current_label") or item.get("label")) or "unlabeled",
                "proposed_label": compact(item.get("proposed_label") or item.get("requested_label")) or "review_needed",
                "severity": compact(item.get("severity")) or "medium",
            }
        )
    return sorted(rows, key=lambda row: (row["dimension"].casefold(), row["id"].casefold()))


def _reviewers(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": compact(item.get("reviewer_id") or item.get("id")) or f"reviewer_{index}",
                "name": compact(item.get("name")) or compact(item.get("reviewer_id") or item.get("id")) or f"reviewer_{index}",
                "capacity": max(int(number(item.get("capacity")) or 0), 0) if "capacity" in item else 999999,
                "assigned": 0,
            }
        )
    return sorted(rows, key=lambda row: row["id"].casefold())


def _assignments(disputes: list[dict[str, Any]], reviewers: list[dict[str, Any]], quorum: int) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    for dispute in disputes:
        selected: list[str] = []
        for reviewer in reviewers:
            if reviewer["assigned"] >= reviewer["capacity"]:
                continue
            selected.append(reviewer["id"])
            reviewer["assigned"] += 1
            if len(selected) == quorum:
                break
        assignments.append(
            {
                "id": f"ELA{len(assignments) + 1}",
                "dispute_id": dispute["id"],
                "dimension": dispute["dimension"],
                "reviewers": selected,
                "quorum_met": len(selected) >= quorum,
                "action": "Assign independent reviewers and collect label rationale.",
            }
        )
    return assignments


def _dimension_groups(disputes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dimensions = sorted({dispute["dimension"] for dispute in disputes}, key=str.casefold)
    return [{"id": f"ELD{index}", "dimension": dimension, "dispute_count": sum(1 for dispute in disputes if dispute["dimension"] == dimension)} for index, dimension in enumerate(dimensions, start=1)]


def _evidence_packets(disputes: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"id": f"ELE{index}", "dispute_id": dispute["id"], "action": "Prepare prompt, output, rubric, current label, proposed label, and source evidence."} for index, dispute in enumerate(disputes, start=1)]


def _quorum_rules(quorum: int) -> list[dict[str, Any]]:
    return [{"id": "ELQ1", "name": "minimum_reviewers", "required_reviewers": quorum}, {"id": "ELQ2", "name": "decision_rule", "description": "Adopt label only when quorum reviewers agree on the disputed dimension."}]


def _tie_break_handling() -> list[dict[str, str]]:
    return [{"id": "ELT1", "name": "tie_breaker", "description": "Escalate split decisions to the evaluation owner for final adjudication."}]


def _audit_trail() -> list[dict[str, str]]:
    return [{"id": "ELL1", "name": "decision_log", "description": "Record reviewer votes, rationale, final label, and timestamp for every dispute."}]
