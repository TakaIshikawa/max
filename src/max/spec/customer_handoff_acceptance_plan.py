"""Generate deterministic customer handoff acceptance plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, records, row, source_summary, values


SCHEMA_VERSION = "max.spec.customer_handoff_acceptance_plan.v1"
KIND = "max.spec.customer_handoff_acceptance_plan"


def generate_customer_handoff_acceptance_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "customer_handoff_acceptance")
    open_items_raw = records(hints.get("open_items") or spec.get("open_items"), [])
    signoffs_raw = records(hints.get("signoffs") or spec.get("signoffs"), ["customer owner", ctx["buyer"]])
    blocking = any(compact(item.get("severity")).lower() in {"critical", "high", "blocking"} or compact(item.get("status")).lower() == "blocking" for item in open_items_raw)
    missing_signoff = any(compact(item.get("status")).lower() in {"", "missing", "pending", "required"} for item in signoffs_raw)
    status = "blocked" if blocking else "pending" if missing_signoff or open_items_raw else "accepted"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, handoff_status=status, open_item_count=len(open_items_raw)),
        "acceptance_scope": [row("CHA", index, name, "handoff_owner", f"Accept customer handoff scope {name}.", evidence_ids) for index, name in enumerate(values(hints.get("acceptance_scope") or spec.get("acceptance_scope"), [ctx["workflow_context"]]), start=1)],
        "receiving_teams": [row("CHT", index, item["name"], compact(item.get("owner")) or "receiving_owner", f"Receive handoff for {item['name']}.", evidence_ids) for index, item in enumerate(records(hints.get("receiving_teams") or spec.get("receiving_teams"), [ctx["target_user"]]), start=1)],
        "open_items": [row("CHO", index, item["name"], compact(item.get("owner")) or "handoff_owner", compact(item.get("description")) or f"Close open item {item['name']}.", evidence_ids, severity=compact(item.get("severity")) or "medium", status=compact(item.get("status")) or "open") for index, item in enumerate(open_items_raw, start=1)],
        "acceptance_checks": [row("CHK", index, item["name"], compact(item.get("owner")) or "handoff_owner", f"Run acceptance check {item['name']}.", evidence_ids, status=compact(item.get("status")) or "required") for index, item in enumerate(records(hints.get("acceptance_checks") or hints.get("checks"), ["documentation complete", "support path confirmed"]), start=1)],
        "signoffs": [row("CHS", index, item["name"], compact(item.get("owner")) or item["name"], f"Capture handoff signoff from {item['name']}.", evidence_ids, status=compact(item.get("status")) or "required", required=True) for index, item in enumerate(signoffs_raw, start=1)],
        "handoff_status": status,
        "evidence_references": ctx["evidence_references"],
    }
