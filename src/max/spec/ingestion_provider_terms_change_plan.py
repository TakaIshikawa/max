"""Generate ingestion provider terms change plans."""

from __future__ import annotations

from datetime import date
from typing import Any

from max.spec._planning_common import compact, context, summary

SCHEMA_VERSION = "max.spec.ingestion_provider_terms_change_plan.v1"
KIND = "max.spec.ingestion_provider_terms_change_plan"


def generate_ingestion_provider_terms_change_plan(spec_like: Any, *, as_of: str | None = None) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    effective = compact(spec.get("effective_date"))
    issues = []
    if effective and effective < (as_of or date.today().isoformat()):
        issues.append("effective_date_in_past")
    if not compact(spec.get("compliance_owner")):
        issues.append("missing_compliance_owner")
    adapters = _adapters(spec.get("affected_adapters") or spec.get("adapters"))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "summary": summary(ctx, provider=compact(spec.get("provider")) or "unknown_provider", effective_date=effective, affected_adapter_count=len(adapters), validation_issue_count=len(issues), risk_level="high" if issues else ctx["risk_level"]), "provider": compact(spec.get("provider")) or "unknown_provider", "effective_date": effective, "affected_adapters": adapters, "allowed_uses": _list(spec.get("allowed_uses")), "policy_deltas": _list(spec.get("policy_deltas") or spec.get("changes")), "retention_changes": _list(spec.get("retention_changes")), "rate_limit_changes": _list(spec.get("rate_limit_changes")), "compliance_review": {"owner": compact(spec.get("compliance_owner")), "status": "blocked" if issues else "required"}, "decision_gates": [{"id": "DG1", "name": "legal_review"}, {"id": "DG2", "name": "adapter_owner_signoff"}, {"id": "DG3", "name": "go_no_go"}], "mitigation_steps": [{"area": "retention", "action": "Update retention policy and purge workflows."}, {"area": "attribution", "action": "Verify provider attribution in downstream publications."}, {"area": "rate_limit", "action": "Tune ingestion schedules to the new provider limits."}], "validation_issues": issues, "evidence_references": ctx["evidence_references"]}


def _adapters(value: Any) -> list[dict[str, str]]:
    rows = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if isinstance(item, dict):
            rows.append({"adapter": compact(item.get("adapter") or item.get("name")) or f"adapter_{index}", "owner": compact(item.get("owner")) or "source_owner", "impact": compact(item.get("impact")) or "review_required"})
        else:
            rows.append({"adapter": compact(item) or f"adapter_{index}", "owner": "source_owner", "impact": "review_required"})
    return sorted(rows, key=lambda row: row["adapter"].casefold())


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [compact(item) for item in value if compact(item)]
    text = compact(value)
    return [text] if text else []
