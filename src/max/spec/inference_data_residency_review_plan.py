"""Generate deterministic inference data residency review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.inference_data_residency_review_plan.v1"
KIND = "max.spec.inference_data_residency_review_plan"


def generate_inference_data_residency_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "inference_data_residency_review")
    inventory = unique_records(named(hints.get("region_inventory") or hints.get("regions"), ("region", "data_category", "residency")), [{"region": "primary inference region", "data_category": "prompt and response payloads", "residency": "unknown"}])
    region_rows = [_region_row(record, index, evidence_ids) for index, record in enumerate(inventory, start=1)]
    findings = [row for row in region_rows if row["review_severity"] in {"medium", "high"}]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, region_count=len(region_rows), review_finding_count=len(findings)),
        "region_inventory": region_rows,
        "transfer_checks": section(hints, ("transfer_checks", "cross_border_checks", "transfers"), "IDT", "privacy_owner", "Review inference data transfer", evidence_ids, ["confirm prompt, completion, embedding, and telemetry paths stay within approved regions"]),
        "provider_controls": section(hints, ("provider_controls", "residency_controls", "providers"), "IDP", "vendor_owner", "Verify provider residency control", evidence_ids, ["provider region pinning, no-training controls, support access controls, and subprocessors"]),
        "log_storage_residency": section(hints, ("log_storage_residency", "logging", "storage"), "IDL", "platform_owner", "Verify log and storage residency", evidence_ids, ["request logs, traces, eval samples, caches, and backups inherit residency policy"]),
        "exception_approvals": section(hints, ("exception_approvals", "exceptions", "approvals"), "IDE", "compliance_owner", "Approve residency exception", evidence_ids, ["document duration, customer scope, legal basis, and compensating controls"]),
        "audit_evidence": section(hints, ("audit_evidence", "evidence", "audit"), "IDA", "compliance_owner", "Collect inference residency audit evidence", evidence_ids, ["provider config export, routing test, log bucket policy, and approval record"]),
        "review_findings": findings,
        "evidence_references": ctx["evidence_references"],
    }


def _region_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    residency = compact(record.get("residency") or record.get("status") or record.get("transfer")).lower()
    severity = "high" if "cross" in residency or "outside" in residency else ("medium" if not residency or residency == "unknown" else "low")
    return row("IDI", index, compact(record.get("name") or record.get("region")) or "primary inference region", compact(record.get("owner")) or "platform_owner", f"Review inference residency for {compact(record.get('data_category') or record.get('category')) or 'prompt and response payloads'}.", evidence_ids, region=compact(record.get("region")), data_category=compact(record.get("data_category") or record.get("category")), residency=residency or "unknown", review_severity=severity)
