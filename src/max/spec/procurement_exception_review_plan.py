"""Generate deterministic procurement exception review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, records, row, source_summary, values


SCHEMA_VERSION = "max.spec.procurement_exception_review_plan.v1"
KIND = "max.spec.procurement_exception_review_plan"


def generate_procurement_exception_review_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "procurement_exception_review")
    exceptions = records(hints.get("exception_reviews") or hints.get("exceptions") or spec.get("exceptions"), ["procurement exception intake"])
    high = any(compact(item.get("severity")).lower() in {"critical", "high"} for item in exceptions)
    expired = any("expired" in compact(item.get("expiration") or item.get("expiry") or item.get("status")).lower() for item in exceptions)
    missing_signoff = any(compact(item.get("status")).lower() in {"", "missing", "pending", "required"} for item in records(hints.get("approver_signoffs") or hints.get("signoffs"), ["procurement owner"]))
    recommendation = "hold" if expired else "conditional" if high or missing_signoff else "approve"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, recommendation=recommendation, exception_count=len(exceptions), high_severity=high, expired=expired),
        "exception_reviews": [row("PER", index, item["name"], compact(item.get("owner")) or "procurement_owner", compact(item.get("description")) or f"Review procurement exception {item['name']}.", evidence_ids, severity=compact(item.get("severity")) or "medium", status=compact(item.get("status")) or "open", expiration=compact(item.get("expiration") or item.get("expiry")) or "not recorded") for index, item in enumerate(exceptions, start=1)],
        "policy_gaps": [row("PEG", index, name, "policy_owner", f"Resolve procurement policy gap: {name}.", evidence_ids, severity="high" if high else "medium") for index, name in enumerate(values(hints.get("policy_gaps") or spec.get("policy_gaps"), ["missing policy mapping"] if high else ["standard exception rationale"]), start=1)],
        "compensating_controls": [row("PEC", index, name, "procurement_owner", f"Operate compensating control: {name}.", evidence_ids) for index, name in enumerate(values(hints.get("compensating_controls") or spec.get("compensating_controls"), ["manual procurement review"]), start=1)],
        "approver_signoffs": [row("PEA", index, item["name"], compact(item.get("owner")) or item["name"], f"Capture approver signoff from {item['name']}.", evidence_ids, status=compact(item.get("status")) or "required", required=True) for index, item in enumerate(records(hints.get("approver_signoffs") or hints.get("signoffs"), ["procurement owner"]), start=1)],
        "expiration_actions": [row("PEX", index, item["name"], compact(item.get("owner")) or "procurement_owner", f"Track expiration for {item['name']}.", evidence_ids, expiration=compact(item.get("expiration") or item.get("expiry")) or "not recorded", action="renew or close before use" if expired else "review before expiration") for index, item in enumerate(exceptions, start=1)],
        "recommendation": recommendation,
        "evidence_references": ctx["evidence_references"],
    }
