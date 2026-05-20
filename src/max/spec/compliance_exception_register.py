"""Generate deterministic compliance exception registers."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, records, row, source_summary, values


SCHEMA_VERSION = "max.spec.compliance_exception_register.v1"
KIND = "max.spec.compliance_exception_register"


def generate_compliance_exception_register(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "compliance_exception_register")
    exceptions = records(hints.get("exceptions") or spec.get("exceptions"), ["compliance exception"])
    gaps = [
        item
        for item in exceptions
        if not compact(item.get("owner")) or not compact(item.get("control")) or not compact(item.get("expiration") or item.get("expiry"))
    ]
    escalations = records(hints.get("escalation_items") or hints.get("escalations"), [gap["name"] for gap in gaps])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, exception_count=len(exceptions), escalation_count=len(escalations)),
        "exceptions": [row("CER", index, item["name"], compact(item.get("owner")) or "missing_owner", compact(item.get("description")) or f"Register compliance exception {item['name']}.", evidence_ids, severity=compact(item.get("severity")) or "medium", control=compact(item.get("control")) or "missing_control", expiration=compact(item.get("expiration") or item.get("expiry")) or "missing_expiration") for index, item in enumerate(exceptions, start=1)],
        "affected_controls": [row("CEC", index, name, "control_owner", f"Assess affected compliance control {name}.", evidence_ids) for index, name in enumerate(values(hints.get("affected_controls"), [compact(item.get("control")) for item in exceptions if compact(item.get("control"))] or ["missing_control"]), start=1)],
        "risk_acceptances": [row("CEA", index, item["name"], compact(item.get("owner")) or "risk_owner", f"Record risk acceptance for {item['name']}.", evidence_ids, status=compact(item.get("status")) or "required") for index, item in enumerate(records(hints.get("risk_acceptances"), [item["name"] for item in exceptions]), start=1)],
        "remediation_actions": [row("CEM", index, name, "control_owner", f"Remediate compliance exception gap: {name}.", evidence_ids) for index, name in enumerate(values(hints.get("remediation_actions"), [gap["name"] for gap in gaps] or ["maintain exception evidence"]), start=1)],
        "review_cadence": compact(hints.get("review_cadence")) or ("weekly" if escalations else "monthly"),
        "escalation_items": [row("CEE", index, item["name"], compact(item.get("owner")) or "compliance_owner", compact(item.get("description")) or f"Escalate incomplete compliance exception {item['name']}.", evidence_ids, severity=compact(item.get("severity")) or "high") for index, item in enumerate(escalations, start=1)],
        "evidence_references": ctx["evidence_references"],
    }
