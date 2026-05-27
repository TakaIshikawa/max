"""Generate deterministic third-party subprocessor review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.third_party_subprocessor_review_plan.v1"
KIND = "max.spec.third_party_subprocessor_review_plan"


def generate_third_party_subprocessor_review_plan(inputs: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(inputs, "third_party_subprocessor_review")
    processors = unique_records(named(hints.get("processors") or hints.get("subprocessors"), ("processor", "vendor", "name")), [{"processor": "unnamed processor", "dpa_status": "missing", "attestation_status": "missing"}])
    inventory = [_processor_row(record, index, evidence_ids) for index, record in enumerate(processors, start=1)]
    findings = [finding for processor in inventory for finding in _processor_findings(processor, len([]), evidence_ids)]
    findings = [row("TPF", index, finding["name"], finding["owner"], finding["description"], evidence_ids, severity=finding["severity"], processor=finding["processor"], required_step=finding["required_step"]) for index, finding in enumerate(findings, start=1)]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, processor_count=len(inventory), risk_finding_count=len(findings)),
        "processor_inventory": inventory,
        "data_categories": section(hints, ("data_categories", "categories"), "TPD", "privacy_owner", "Review data category", evidence_ids, ["customer content, account data, telemetry, and support data"]),
        "customer_notice_requirements": section(hints, ("customer_notice_requirements", "notices"), "TPN", "legal_owner", "Confirm customer notice requirement", evidence_ids, ["notice period, processor list update, and opt-out process if applicable"]),
        "renewal_dates": section(hints, ("renewal_dates", "renewals"), "TPR", "procurement_owner", "Track subprocessor renewal date", evidence_ids, ["renewal owner, security refresh, DPA refresh, and termination path"]),
        "risk_findings": findings,
        "evidence_references": ctx["evidence_references"],
    }


def _processor_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    name = compact(record.get("processor") or record.get("vendor") or record.get("name")) or f"processor-{index}"
    alias = compact(record.get("alias")) or name
    return row("TPI", index, alias, compact(record.get("owner")) or "vendor_owner", "Review third-party subprocessor privacy and security posture.", evidence_ids, processor=name, alias=alias, data_categories=compact(record.get("data_categories") or record.get("data_category")) or "unknown", residency=compact(record.get("residency") or record.get("region")) or "unknown", dpa_status=compact(record.get("dpa_status") or record.get("dpa")) or "missing", scc_status=compact(record.get("scc_status") or record.get("scc")) or "unknown", security_attestation=compact(record.get("security_attestation") or record.get("attestation_status") or record.get("attestation")) or "missing")


def _processor_findings(processor: dict[str, Any], _offset: int, evidence_ids: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if processor["dpa_status"].lower() in {"missing", "unknown", "expired"}:
        findings.append(row("TPX", 1, f"missing DPA for {processor['processor']}", "legal_owner", "Subprocessor requires current DPA before approval.", evidence_ids, severity="high", processor=processor["processor"], required_step="collect executed DPA"))
    if "cross" in processor["residency"].lower() or "outside" in processor["residency"].lower():
        findings.append(row("TPX", 1, f"cross-border review for {processor['processor']}", "privacy_owner", "Cross-border processing requires SCC/TIA and customer notice review.", evidence_ids, severity="high", processor=processor["processor"], required_step="complete transfer impact assessment"))
    if processor["security_attestation"].lower() in {"missing", "stale", "expired", "unknown"}:
        findings.append(row("TPX", 1, f"stale attestation for {processor['processor']}", "security_owner", "Subprocessor requires current security attestation evidence.", evidence_ids, severity="medium", processor=processor["processor"], required_step="collect SOC 2 or equivalent attestation"))
    return findings
