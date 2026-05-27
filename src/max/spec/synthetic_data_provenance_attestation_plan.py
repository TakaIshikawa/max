"""Generate deterministic synthetic data provenance attestation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.synthetic_data_provenance_attestation_plan.v1"
KIND = "max.spec.synthetic_data_provenance_attestation_plan"


def generate_synthetic_data_provenance_attestation_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "synthetic_data_provenance_attestation")
    datasets = unique_records(named(hints.get("dataset_inventory") or hints.get("datasets"), ("dataset_id", "dataset", "source", "generator")), [{"dataset_id": "synthetic dataset", "source": "unknown", "generator": "unknown"}])
    inventory = [_dataset_row(record, index, evidence_ids) for index, record in enumerate(datasets, start=1)]
    findings = _findings(inventory, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, dataset_count=len(inventory), review_finding_count=len(findings)),
        "dataset_inventory": inventory,
        "generation_methods": section(hints, ("generation_methods", "methods", "generators"), "SDM", "data_science_owner", "Document synthetic generation method", evidence_ids, ["model, prompt template, seed source, filtering, and quality controls"]),
        "source_constraints": section(hints, ("source_constraints", "constraints", "source_limits"), "SDC", "data_governance_owner", "Document source data constraint", evidence_ids, ["license, consent, retention, lineage, and excluded sensitive source limits"]),
        "privacy_attestations": section(hints, ("privacy_attestations", "privacy", "attestations"), "SDP", "privacy_owner", "Attest synthetic data privacy", evidence_ids, ["no direct personal data reconstruction, k-anonymity check, and memorization review"]),
        "permitted_uses": section(hints, ("permitted_uses", "uses", "allowed_uses"), "SDU", "data_owner", "Define permitted synthetic data use", evidence_ids, ["evaluation, testing, demos, and development environments only"]),
        "retention_controls": section(hints, ("retention_controls", "retention"), "SDR", "data_owner", "Control synthetic data retention", evidence_ids, ["expiry, storage location, deletion owner, and access review cadence"]),
        "approval_evidence": section(hints, ("approval_evidence", "approvals", "approval"), "SDA", "governance_owner", "Collect synthetic data approval evidence", evidence_ids, ["data owner, privacy, security, and legal approval records"]),
        "review_findings": findings,
        "evidence_references": ctx["evidence_references"],
    }


def _dataset_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    dataset_id = compact(record.get("dataset_id") or record.get("id") or record.get("name") or record.get("dataset"))
    return row("SDI", index, dataset_id or "synthetic dataset", compact(record.get("owner")) or "data_owner", "Attest synthetic dataset provenance before use.", evidence_ids, dataset_id=dataset_id or "synthetic dataset", source=compact(record.get("source") or record.get("origin")), generator=compact(record.get("generator") or record.get("generation_method")), privacy_attestation=compact(record.get("privacy_attestation") or record.get("privacy")))


def _findings(inventory: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for dataset in inventory:
        if dataset.get("source", "").lower() in {"", "unknown"}:
            findings.append(row("SDF", len(findings) + 1, f"missing provenance for {dataset['dataset_id']}", "data_governance_owner", "Dataset needs documented source provenance before approval.", evidence_ids, severity="high", dataset_id=dataset["dataset_id"]))
        if not dataset.get("privacy_attestation"):
            findings.append(row("SDF", len(findings) + 1, f"missing privacy attestation for {dataset['dataset_id']}", "privacy_owner", "Dataset needs privacy attestation before permitted use.", evidence_ids, severity="medium", dataset_id=dataset["dataset_id"]))
    return findings
