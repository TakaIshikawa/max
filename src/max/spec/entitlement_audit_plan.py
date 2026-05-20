"""Generate deterministic entitlement audit plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, records, row, source_summary, values


SCHEMA_VERSION = "max.spec.entitlement_audit_plan.v1"
KIND = "max.spec.entitlement_audit_plan"


def generate_entitlement_audit_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "entitlement_audit")
    sampled_accounts = records(hints.get("sampled_accounts") or spec.get("sampled_accounts"), [ctx["target_user"]])
    findings = records(hints.get("mismatch_findings") or hints.get("findings"), [])
    critical = any(compact(item.get("severity")).lower() in {"critical", "high"} for item in findings)
    missing_owner = any(not compact(item.get("owner")) for item in sampled_accounts)
    outcome = "failed" if critical else "conditional" if findings or missing_owner else "passed"

    scope_names = values(hints.get("entitlement_scope") or hints.get("scope") or spec.get("entitlement_scope"), [ctx["workflow_context"]])
    scope = [
        row("EAS", index, name, "access_owner", f"Audit entitlement coverage for {name}.", evidence_ids, severity="high" if critical else "medium")
        for index, name in enumerate(scope_names, start=1)
    ]
    accounts = [
        row("EAA", index, item["name"], compact(item.get("owner")) or "missing_owner", f"Sample account {item['name']} for entitlement fit.", evidence_ids, entitlement=compact(item.get("entitlement")) or "primary access")
        for index, item in enumerate(sampled_accounts, start=1)
    ]
    mismatch_findings = [
        row("EAF", index, item["name"], compact(item.get("owner")) or "access_owner", compact(item.get("description")) or f"Resolve entitlement mismatch for {item['name']}.", evidence_ids, severity=compact(item.get("severity")) or "medium", account=compact(item.get("account")))
        for index, item in enumerate(findings, start=1)
    ]
    remediation_actions = [
        row("EAR", index, item["name"], compact(item.get("owner")) or "access_owner", f"Remediate entitlement finding: {item['name']}.", evidence_ids, severity=compact(item.get("severity")) or "medium", timing=compact(item.get("due")) or "before audit closure")
        for index, item in enumerate(findings or ([{"name": "confirm sampled access remains appropriate"}] if outcome == "conditional" else []), start=1)
    ]
    attestations = [
        row("EAO", index, compact(item.get("owner")) or "access_owner", compact(item.get("owner")) or "access_owner", f"Attest sampled entitlement for {item['name']}.", evidence_ids, required=True)
        for index, item in enumerate(sampled_accounts, start=1)
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, audit_outcome=outcome, sampled_account_count=len(accounts), mismatch_count=len(mismatch_findings)),
        "entitlement_scope": scope,
        "sampled_accounts": accounts,
        "mismatch_findings": mismatch_findings,
        "remediation_actions": remediation_actions,
        "owner_attestations": attestations,
        "audit_outcome": outcome,
        "evidence_references": ctx["evidence_references"],
    }
