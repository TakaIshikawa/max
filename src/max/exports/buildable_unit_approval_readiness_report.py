"""Buildable unit approval readiness export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.buildable_unit_approval_readiness_report.v1"
KIND = "max.buildable_unit_approval_readiness_report"

_STATUS_ORDER = {"blocked": 0, "needs_review": 1, "ready": 2}


def generate_buildable_unit_approval_readiness_report(units: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for index, raw in enumerate(units):
        recommendation = _text(raw.get("recommendation") or raw.get("evaluation_recommendation")).lower()
        evidence_count = _count(raw.get("evidence_count"), raw.get("evidence") or raw.get("evidence_items"))
        acceptance_criteria_count = _count(raw.get("acceptance_criteria_count"), raw.get("acceptance_criteria") or raw.get("criteria"))
        blocker_count = _count(raw.get("blocker_count"), raw.get("blockers") or raw.get("spec_blockers"))
        status = _status(recommendation, evidence_count, acceptance_criteria_count, blocker_count)
        rows.append(
            {
                "unit_id": _text(raw.get("unit_id") or raw.get("id")) or f"unit-{index + 1}",
                "recommendation": recommendation or "unknown",
                "evidence_count": evidence_count,
                "acceptance_criteria_count": acceptance_criteria_count,
                "blocker_count": blocker_count,
                "status": status,
            }
        )
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["unit_id"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "unit_count": len(rows),
            "ready_count": sum(1 for row in rows if row["status"] == "ready"),
            "needs_review_count": sum(1 for row in rows if row["status"] == "needs_review"),
            "blocked_count": sum(1 for row in rows if row["status"] == "blocked"),
        },
        "rows": rows,
    }


def _status(recommendation: str, evidence_count: int, acceptance_criteria_count: int, blocker_count: int) -> str:
    if blocker_count > 0 or recommendation in {"reject", "rejected", "block", "blocked"}:
        return "blocked"
    if recommendation in {"approve", "approved", "ready"} and evidence_count > 0 and acceptance_criteria_count > 0:
        return "ready"
    return "needs_review"


def _count(explicit: Any, collection: Any) -> int:
    value = _int(explicit)
    if value:
        return value
    if collection is None or collection == "":
        return 0
    if isinstance(collection, (list, tuple, set, dict)):
        return len(collection)
    return 1


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
