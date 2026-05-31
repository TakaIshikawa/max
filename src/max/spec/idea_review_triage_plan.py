"""Generate deterministic idea review triage plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.idea_review_triage_plan.v1"
KIND = "max.spec.idea_review_triage_plan"


def generate_idea_review_triage_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    ideas = _ideas(hints.get("ideas") or hints.get("reviews") or spec.get("ideas") or spec.get("reviews"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, pending_idea_count=len(ideas), stale_idea_count=sum(1 for item in ideas if item["stale"])),
        "triage_queue": ideas,
        "reviewer_queues": _reviewer_queues(ideas),
        "escalation_criteria": _escalation_criteria(),
        "completion_checks": _completion_checks(),
        "evidence_references": ctx["evidence_references"],
    }


def _ideas(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        status = compact(item.get("status") or item.get("review_status")).casefold() or "pending"
        if status in {"approved", "rejected"}:
            continue
        age_hours = float(number(item.get("age_hours") or item.get("pending_hours") or item.get("stale_hours")) or 0.0)
        score = float(number(item.get("score") or item.get("review_score") or item.get("value_score")) or 0.0)
        rows.append(
            {
                "id": compact(item.get("id") or item.get("idea_id")) or f"IRT{index}",
                "profile": compact(item.get("profile")) or "default",
                "status": status,
                "age_hours": age_hours,
                "score": score,
                "stale": bool(item.get("stale")) or age_hours >= 72,
                "reviewer_hint": compact(item.get("reviewer") or item.get("owner")) or _reviewer_hint(score, age_hours),
            }
        )
    return sorted(rows, key=lambda row: (0 if row["stale"] else 1, -row["score"], -row["age_hours"], row["profile"].casefold(), row["id"].casefold()))


def _reviewer_queues(ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviewers = sorted({item["reviewer_hint"] for item in ideas}, key=str.casefold) or ["no_pending_reviewer"]
    return [
        {"id": f"IRQ{index}", "reviewer": reviewer, "idea_ids": [item["id"] for item in ideas if item["reviewer_hint"] == reviewer], "action": "review assigned pending ideas" if ideas else "confirm no pending ideas require triage"}
        for index, reviewer in enumerate(reviewers, start=1)
    ]


def _escalation_criteria() -> list[dict[str, str]]:
    return [
        {"id": "IRE1", "name": "stale_high_score", "condition": "pending idea is older than 72 hours with score >= 0.75", "action": "escalate to lead reviewer"},
        {"id": "IRE2", "name": "blocked_assignment", "condition": "reviewer queue has no movement for one business day", "action": "reassign to backup reviewer"},
    ]


def _completion_checks() -> list[dict[str, str]]:
    return [
        {"id": "IRC1", "name": "pending_queue_empty", "target": "all triaged ideas are approved, rejected, or explicitly deferred"},
        {"id": "IRC2", "name": "decision_notes", "target": "every completed review has rationale and reviewer id"},
    ]


def _reviewer_hint(score: float, age_hours: float) -> str:
    if age_hours >= 72 or score >= 0.8:
        return "lead_reviewer"
    return "standard_reviewer"


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("idea_review_triage")
    return hints if isinstance(hints, dict) else {}
