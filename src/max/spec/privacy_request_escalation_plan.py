"""Generate deterministic privacy request escalation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.privacy_request_escalation_plan.v1"
KIND = "max.spec.privacy_request_escalation_plan"


def generate_privacy_request_escalation_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "privacy_request_escalation")
    requests = unique_records(
        named(hints.get("requests") or hints.get("requester_scope"), ("requester", "request_type", "jurisdiction")),
        [{"name": "privacy request escalation", "owner": "privacy_owner", "severity": "medium", "deadline": "not recorded"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, request_count=len(requests)),
        "request_scope": [
            item("PRE", index, record, "privacy_owner", evidence_ids, "Review privacy request scope", name_keys=("name", "requester", "request_type", "jurisdiction"), extra_keys=("requester", "request_type", "jurisdiction", "sla_risk"))
            for index, record in enumerate(requests, start=1)
        ],
        "sla_risk": section(hints, ("sla_risk", "due_dates", "deadlines"), "PRS", "privacy_owner", "Track privacy request SLA risk", evidence_ids, ["statutory due date and breach risk"]),
        "blockers": section(hints, ("blockers",), "PRB", "escalation_owner", "Clear privacy request blocker", evidence_ids, ["no active blockers; verify dependencies remain clear"]),
        "evidence_needed": section(hints, ("evidence", "evidence_needed"), "PRV", "data_owner", "Collect privacy request evidence", evidence_ids, ["identity, scope, fulfillment, and exemption evidence"]),
        "escalation_owners": section(hints, ("owners", "escalation_owners"), "PRO", "privacy_owner", "Assign escalation owner", evidence_ids, ["privacy, legal, security, and data owner assignments"]),
        "communications": section(hints, ("communications", "customer_communications", "legal_communications"), "PRC", "legal_owner", "Coordinate privacy request communications", evidence_ids, ["requester, legal, security, and customer communication"]),
        "closure_proof": section(hints, ("closure", "closure_proof"), "PRX", "privacy_owner", "Capture closure proof", evidence_ids, ["fulfillment receipt, exemption record, and audit trail"]),
        "evidence_references": ctx["evidence_references"],
    }
