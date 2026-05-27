"""Generate deterministic inference rate limit exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.inference_rate_limit_exception_plan.v1"
KIND = "max.spec.inference_rate_limit_exception_plan"


def generate_inference_rate_limit_exception_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "inference_rate_limit_exception")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    exceptions = unique_records(
        named(hints.get("exceptions") or hints.get("requests") or hints.get("rate_limit_exceptions"), ("request", "model", "tenant", "name")),
        [{"name": "temporary inference rate limit exception", "owner": "platform_owner", "severity": "medium"}],
    )
    rows = [_exception("IRX", index, record, evidence_ids) for index, record in enumerate(exceptions, start=1)]
    blockers = _rate_limit_blockers(rows, evidence_ids)
    warnings = _warnings(rows, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Inference Rate Limit Exception Plan",
        "summary": source_summary(ctx, exception_count=len(rows), blocker_count=len(blockers), warning_count=len(warnings)),
        "exception_requests": rows,
        "business_justification": section(hints, ("business_justification", "justification"), "IRJ", "requester", "Document business justification", evidence_ids, [row.get("business_justification") or row["name"] for row in rows]),
        "limit_delta": [
            row("IRD", index, request["name"], request["owner"], f"Change inference limit from {request.get('current_limit', 'unspecified')} to {request.get('proposed_limit', 'unspecified')}.", evidence_ids, severity=request.get("severity", "medium"), current_limit=request.get("current_limit"), proposed_limit=request.get("proposed_limit"))
            for index, request in enumerate(rows, start=1)
        ],
        "budget_impact": section(hints, ("budget_impact", "budget"), "IRB", "finance_owner", "Review budget impact", evidence_ids, [row.get("budget_impact") or "estimate incremental inference spend and quota burn" for row in rows]),
        "safety_monitoring": section(hints, ("safety_monitoring", "monitoring"), "IRM", "trust_safety_owner", "Monitor temporary inference exception", evidence_ids, [row.get("safety_monitoring") or "monitor abuse, latency, spend, and model safety metrics during exception" for row in rows]),
        "expiry": section(hints, ("expiry", "expiration"), "IRE", "platform_owner", "Confirm exception expiry", evidence_ids, [row.get("expiry") or "time-boxed expiry required" for row in rows]),
        "approval_gates": section(hints, ("approval_gates", "approvals", "approvers"), "IRA", "approval_owner", "Approve inference rate limit exception", evidence_ids, ["requester manager, platform owner, finance, and trust safety approval"]),
        "rollback": section(hints, ("rollback", "rollback_criteria"), "IRR", "platform_owner", "Define inference rate limit rollback", evidence_ids, ["restore prior limit on expiry, budget breach, abuse signal, latency regression, or approval withdrawal"]),
        "blockers": blockers,
        "warnings": warnings,
        "evidence_references": ctx["evidence_references"],
    }


def _exception(prefix: str, index: int, record: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    data = item(prefix, index, record, "platform_owner", evidence_ids, "Review inference rate limit exception", name_keys=("name", "request", "model", "tenant"), extra_keys=("requester", "business_justification", "current_limit", "proposed_limit", "budget_impact", "safety_monitoring", "expiry", "approver", "evidence_id"))
    if isinstance(record.get("metadata"), dict):
        data["metadata"] = dict(sorted(record["metadata"].items()))
    return data


def _rate_limit_blockers(rows: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for request in rows:
        for field in ("expiry", "approver"):
            if not compact(request.get(field)):
                blockers.append(row("IRK", len(blockers) + 1, f"missing {field} for {request['name']}", "platform_owner", f"Temporary inference rate limit exception must include {field}.", evidence_ids, severity="high", request=request["name"], missing_field=field))
    return blockers


def _warnings(rows: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for request in rows:
        if not compact(request.get("budget_impact")):
            warnings.append(row("IRW", len(warnings) + 1, f"missing budget impact for {request['name']}", "finance_owner", "Budget impact should be estimated before approval.", evidence_ids, severity="medium", request=request["name"]))
        if not compact(request.get("safety_monitoring")):
            warnings.append(row("IRW", len(warnings) + 1, f"missing safety monitoring for {request['name']}", "trust_safety_owner", "Safety monitoring should be defined before the temporary limit increase starts.", evidence_ids, severity="medium", request=request["name"]))
    return warnings
