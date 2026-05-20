"""Generate deterministic data residency transfer assessment plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, records, row, source_summary, values


SCHEMA_VERSION = "max.spec.data_residency_transfer_assessment_plan.v1"
KIND = "max.spec.data_residency_transfer_assessment_plan"


def generate_data_residency_transfer_assessment_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "data_residency_transfer_assessment")
    paths = records(hints.get("transfer_paths") or spec.get("transfer_paths"), [ctx["workflow_context"]])
    constraints = values(hints.get("residency_constraints") or spec.get("residency_constraints"), ["confirm residency constraints"])
    approvals = records(hints.get("approval_requirements") or spec.get("approval_requirements"), ["privacy approval"])
    restricted = any(term in " ".join([compact(path.get("to")) + " " + compact(path.get("region")) for path in paths] + constraints).lower() for term in ("restricted", "china", "russia", "unknown", "unapproved"))
    missing_approval = any(compact(item.get("status")).lower() in {"", "missing", "pending", "required"} for item in approvals)
    decision = "blocked" if restricted and missing_approval else "conditional" if restricted or missing_approval else "approved"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, transfer_decision=decision, transfer_path_count=len(paths), restricted=restricted),
        "transfer_paths": [row("DRP", index, item["name"], compact(item.get("owner")) or "data_owner", f"Assess transfer path {item['name']}.", evidence_ids, from_region=compact(item.get("from")), to_region=compact(item.get("to") or item.get("region"))) for index, item in enumerate(paths, start=1)],
        "residency_constraints": [row("DRC", index, name, "privacy_owner", f"Validate residency constraint {name}.", evidence_ids, severity="high" if "restricted" in name.lower() else "medium") for index, name in enumerate(constraints, start=1)],
        "approval_requirements": [row("DRA", index, item["name"], compact(item.get("owner")) or "privacy_owner", f"Collect approval for {item['name']}.", evidence_ids, status=compact(item.get("status")) or "required") for index, item in enumerate(approvals, start=1)],
        "risk_items": [row("DRR", index, item["name"], compact(item.get("owner")) or "privacy_owner", compact(item.get("description")) or f"Track transfer risk {item['name']}.", evidence_ids, severity=compact(item.get("severity")) or "high") for index, item in enumerate(records(hints.get("risk_items"), [] if decision == "approved" else ["restricted transfer or missing approval"]), start=1)],
        "mitigation_actions": [row("DRM", index, name, "privacy_owner", f"Mitigate transfer issue: {name}.", evidence_ids) for index, name in enumerate(values(hints.get("mitigation_actions"), ["collect transfer approval"] if decision != "approved" else ["retain transfer assessment evidence"]), start=1)],
        "transfer_decision": decision,
        "evidence_references": ctx["evidence_references"],
    }
