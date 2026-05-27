"""Generate deterministic production access request plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.production_access_request_plan.v1"
KIND = "max.spec.production_access_request_plan"


def generate_production_access_request_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "production_access_request")
    systems = unique_records(named(hints.get("systems") or hints.get("production_systems"), ("system", "name")), [{"system": "production system"}])
    access_level = compact(hints.get("access_level") or hints.get("level") or "read-only")
    privileged = access_level.lower() in {"admin", "privileged", "write", "break-glass", "owner"}
    blockers = _blockers(hints, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, requester=compact(hints.get("requester")) or "missing", access_level=access_level, privileged_access=privileged, blocker_count=len(blockers)),
        "requester": compact(hints.get("requester")) or "missing",
        "systems": [row("PAS", index, compact(record.get("system") or record.get("name")) or "production system", compact(record.get("owner")) or "system_owner", "Review requested production system access.", evidence_ids, access_level=access_level) for index, record in enumerate(systems, start=1)],
        "business_justification": compact(hints.get("business_justification") or hints.get("justification")) or "missing",
        "duration": compact(hints.get("duration") or hints.get("expires_at")) or "missing",
        "approvers": section(hints, ("approvers", "approval_path"), "PAA", "access_owner", "Approve production access request", evidence_ids, ["manager, system owner, security, and privacy if data access is involved"]),
        "compensating_controls": section(hints, ("compensating_controls", "controls"), "PAC", "security_owner", "Apply compensating access control", evidence_ids, ["JIT grant, MFA, session recording, ticket link, and command logging"]),
        "recertification": row("PAR", 1, "recertification check", "access_owner", "Confirm access expiration and recertification.", evidence_ids, recertification_date=compact(hints.get("recertification_date")) or "at access expiry"),
        "validation_checks": ["privileged access requires session recording and security approval"] if privileged else ["standard access requires owner approval and expiry"],
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _blockers(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    required = (("requester", "missing requester"), ("approvers", "missing approver"), ("duration", "missing duration"), ("business_justification", "missing business justification"))
    blockers: list[dict[str, Any]] = []
    for key, label in required:
        value = hints.get(key) or (hints.get("justification") if key == "business_justification" else None)
        if not value:
            blockers.append(row("PAB", len(blockers) + 1, label, "access_owner", f"Resolve {label} before production access approval.", evidence_ids, severity="high"))
    return blockers
