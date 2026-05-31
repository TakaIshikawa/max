"""Generate deterministic data processor exit plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.data_processor_exit_plan.v1"
KIND = "max.spec.data_processor_exit_plan"


def generate_data_processor_exit_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "data_processor_exit")
    processors = unique_records(named(hints.get("processors") or hints.get("processor_inventory"), ("processor", "vendor", "name")), [{"name": "processor exit inventory bootstrap", "replacement_owner": "missing"}])
    processors = sorted(processors, key=lambda row: (_risk(row), compact(row.get("name")).casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Data Processor Exit Plan", "summary": source_summary(ctx, processor_count=len(processors), high_risk_processor_count=sum(1 for row in processors if _risk(row) == 0)), "processor_inventory": [item("DPE", i, row, "vendor_owner", evidence_ids, "Inventory data processor exit", name_keys=("name", "processor", "vendor"), extra_keys=("data_class", "replacement_owner", "deletion_attestation")) for i, row in enumerate(processors, 1)], "exit_trigger": section(hints, ("exit_trigger", "triggers"), "DPT", "vendor_owner", "Define processor exit trigger", evidence_ids, ["contract termination, risk finding, product migration, incident response, or customer requirement"]), "replacement_readiness": _readiness(processors, evidence_ids), "data_transfer": section(hints, ("data_transfer", "export"), "DPX", "data_owner", "Transfer processor data", evidence_ids, ["export data, reconcile counts, validate replacement import, and preserve audit logs"]), "deletion_attestation": _attestation(processors, evidence_ids), "access_revocation": section(hints, ("access_revocation", "revocation"), "DPA", "security_owner", "Revoke processor access", evidence_ids, ["revoke users, API keys, network paths, webhooks, and support access"]), "contract_obligations": section(hints, ("contract_obligations", "contracts"), "DPC", "legal_owner", "Close processor contract obligation", evidence_ids, ["notice periods, data return, deletion SLA, audit rights, and subprocessor flow-down terms"]), "customer_impact": section(hints, ("customer_impact", "impact"), "DPI", "customer_owner", "Assess customer impact", evidence_ids, ["customer data scope, downtime, notices, support paths, and contractual commitments"]), "stakeholder_signoff": section(hints, ("stakeholder_signoff", "signoff"), "DPS", "vendor_owner", "Approve processor exit", evidence_ids, ["vendor, legal, security, data, product, and customer owner signoff"]), "evidence_references": ctx["evidence_references"]}


def _risk(row: dict[str, Any]) -> int:
    text = f"{compact(row.get('data_class'))} {compact(row.get('data_type'))}".lower()
    return 0 if any(term in text for term in ("regulated", "customer", "pii", "phi")) else 1


def _readiness(processors: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [item("DPR", i, {"name": compact(row.get("name")), "severity": "high" if not compact(row.get("replacement_owner")) or compact(row.get("replacement_owner")).lower() == "missing" else "medium", "description": "Assign replacement owner before exit execution." if not compact(row.get("replacement_owner")) or compact(row.get("replacement_owner")).lower() == "missing" else "Confirm replacement service readiness and migration owner."}, "product_owner", evidence_ids, "Check processor replacement readiness") for i, row in enumerate(processors, 1)]


def _attestation(processors: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [item("DPD", i, {"name": compact(row.get("name")), "severity": "high" if compact(row.get("deletion_attestation")).lower() in {"", "missing", "no"} else "medium", "description": "Obtain deletion attestation before final processor offboarding." if compact(row.get("deletion_attestation")).lower() in {"", "missing", "no"} else "Verify deletion attestation scope and retention exceptions."}, "vendor_owner", evidence_ids, "Verify processor deletion attestation") for i, row in enumerate(processors, 1)]
