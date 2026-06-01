"""Generate buildable unit graduation criteria plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base

SCHEMA_VERSION = "max.spec.buildable_unit_graduation_criteria_plan.v1"
KIND = "max.spec.buildable_unit_graduation_criteria_plan"


def generate_buildable_unit_graduation_criteria_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "buildable_unit_graduation_criteria")
    units = _rows(hints) or _rows(spec)
    candidates = [_candidate(row, i, evidence_ids, hints) for i, row in enumerate(units, 1)]
    ready = [u for u in candidates if u["status"] == "ready"]
    blocked = [u for u in candidates if u["status"] == "blocked"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": {"ready_count": len(ready), "blocked_count": len(blocked), "needs_review_count": sum(1 for u in candidates if u["status"] == "needs_review")},
        "graduation_candidates": candidates,
        "blocker_remediation": [{"id": f"BUGR{i}", "unit_id": u["unit_id"], "action": "resolve blockers before graduation gate is scheduled", "owner": u["owner"], "evidence_reference_ids": evidence_ids} for i, u in enumerate(blocked, 1)],
        "graduation_gates": [{"id": f"BUGG{i}", "unit_id": u["unit_id"], "check": "score, evidence, readiness, and signoff thresholds met", "evidence_reference_ids": evidence_ids} for i, u in enumerate(ready, 1)],
        "stakeholder_signoffs": [{"id": f"BUGS{i}", "unit_id": u["unit_id"], "owner": u["owner"], "signoff": "graduation approval", "evidence_reference_ids": evidence_ids} for i, u in enumerate(candidates or [{"unit_id": "none", "owner": "product_owner"}], 1)],
        "verification_gates": [{"id": "BUGV1", "check": "graduated units have no open blockers and meet evidence threshold", "evidence_reference_ids": evidence_ids}],
        "evidence_references": ctx["evidence_references"],
    }


def _rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    value = source.get("units") if isinstance(source, dict) else None
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _candidate(row: dict[str, Any], index: int, evidence_ids: list[str], hints: dict[str, Any]) -> dict[str, Any]:
    min_score = float(hints.get("minimum_score", 0.8))
    min_evidence = int(hints.get("minimum_evidence_count", 2))
    score = _float(row.get("evaluation_score") or row.get("score"))
    evidence_count = int(_float(row.get("evidence_count") or len(row.get("evidence", []) if isinstance(row.get("evidence"), list) else [])))
    ready_flag = bool(row.get("spec_ready") or row.get("ready"))
    blockers = row.get("blockers") if isinstance(row.get("blockers"), list) else []
    status = "blocked" if blockers or row.get("blocked") else "ready" if score >= min_score and evidence_count >= min_evidence and ready_flag else "needs_review"
    return {"id": f"BUG{index}", "unit_id": compact(row.get("id") or row.get("unit_id") or row.get("name")) or f"unit-{index}", "owner": compact(row.get("owner")) or "product_owner", "evaluation_score": score, "evidence_count": evidence_count, "spec_ready": ready_flag, "status": status, "evidence_reference_ids": evidence_ids}


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
