"""Generate publication approval delegation plans."""

from __future__ import annotations

from datetime import date
from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base

SCHEMA_VERSION = "max.spec.publication_approval_delegation_plan.v1"
KIND = "max.spec.publication_approval_delegation_plan"


def generate_publication_approval_delegation_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "publication_approval_delegation")
    rows = _rows(hints) or _rows(spec)
    matrix = sorted((_delegation(row, i, evidence_ids) for i, row in enumerate(rows, 1)), key=lambda r: (_risk_rank(r["risk_level"]), r["destination"]))
    blocked = [row for row in matrix if row["blocking"]]
    high = [row for row in matrix if row["risk_level"] in {"critical", "high"}]
    highest = matrix[0]["destination"] if matrix else "none"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": {"title": ctx["title"], "blocked_delegation_count": len(blocked), "highest_risk_destination": highest, "destination_count": len(matrix)},
        "delegation_matrix": matrix,
        "escalation_paths": [{"id": f"PDE{i}", "destination": row["destination"], "owner": row["owner"], "action": "route publication approval to backup delegate and compliance reviewer", "evidence_reference_ids": evidence_ids} for i, row in enumerate(high or blocked or matrix[:1], 1)],
        "audit_checks": [{"id": f"PDA{i}", "destination": row["destination"], "check": "verify delegate is active, unblocked, and inside approval window", "evidence_reference_ids": evidence_ids} for i, row in enumerate(high or matrix[:1], 1)],
        "verification_gates": [{"id": "PDG1", "check": "all blocking delegation issues have named active delegates", "evidence_reference_ids": evidence_ids}],
        "evidence_references": ctx["evidence_references"],
    }


def _rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("approvals", "destinations", "delegations", "rows"):
        value = source.get(key) if isinstance(source, dict) else None
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _delegation(row: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    destination = compact(row.get("destination") or row.get("name") or row.get("id")) or f"destination-{index}"
    delegate = compact(row.get("delegate") or row.get("delegated_approver"))
    expiry = compact(row.get("expires_at") or row.get("expiration") or row.get("end_at"))
    expired = bool(expiry and expiry[:10] < date.today().isoformat())
    blocked_approver = bool(row.get("blocked") or compact(row.get("approver_status")).lower() == "blocked")
    high_risk = bool(row.get("high_risk") or compact(row.get("risk")).lower() in {"high", "critical"})
    blocking = not delegate or expired or blocked_approver
    risk = "critical" if blocking and high_risk else "high" if blocking or high_risk else "low"
    return {"id": f"PDD{index}", "destination": destination, "delegate": delegate, "owner": compact(row.get("owner")) or "publication_owner", "blocking": blocking, "risk_level": risk, "issues": [issue for issue, present in (("missing_delegate", not delegate), ("expired_window", expired), ("blocked_approver", blocked_approver), ("high_risk_destination", high_risk)) if present], "evidence_reference_ids": evidence_ids}


def _risk_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)
