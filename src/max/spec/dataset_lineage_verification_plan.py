"""Generate deterministic dataset lineage verification plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.dataset_lineage_verification_plan.v1"
KIND = "max.spec.dataset_lineage_verification_plan"


def generate_dataset_lineage_verification_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "dataset_lineage_verification")
    datasets = unique_records(named(hints.get("datasets") or hints.get("dataset_inventory"), ("dataset", "dataset_id", "name")), [{"dataset": "unnamed dataset"}])
    inventory = [_dataset_row(record, index, evidence_ids) for index, record in enumerate(datasets, start=1)]
    blockers = [blocker for dataset in inventory for blocker in _blockers(dataset, evidence_ids)]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, dataset_count=len(inventory), blocker_count=len(blockers)),
        "datasets": inventory,
        "upstream_sources": section(hints, ("upstream_sources", "sources"), "DLU", "data_owner", "Verify upstream source", evidence_ids, ["source system, owner, extraction time, and retention policy"]),
        "transformation_steps": section(hints, ("transformation_steps", "transformations"), "DLT", "data_engineering_owner", "Verify transformation step", evidence_ids, ["job name, code version, inputs, outputs, and quality checks"]),
        "verification_checks": section(hints, ("verification_checks", "checks"), "DLV", "data_quality_owner", "Run lineage verification check", evidence_ids, ["owner present, sources documented, license/consent approved, and refresh cadence current"]),
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _dataset_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    name = compact(record.get("dataset") or record.get("dataset_id") or record.get("name")) or "unnamed dataset"
    return row("DLI", index, name, compact(record.get("owner")) or "missing", "Verify dataset lineage before use.", evidence_ids, dataset=name, upstream_source=compact(record.get("upstream_source") or record.get("source")) or "missing", refresh_cadence=compact(record.get("refresh_cadence") or record.get("cadence")) or "unknown", license_status=compact(record.get("license_status") or record.get("license") or record.get("consent_status") or record.get("consent")) or "missing")


def _blockers(dataset: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    checks = (("owner", "missing owner"), ("upstream_source", "missing upstream source"), ("license_status", "missing license or consent"))
    return [row("DLB", index, f"{label} for {dataset['dataset']}", "data_governance_owner", f"Resolve {label} before lineage approval.", evidence_ids, severity="high", dataset=dataset["dataset"]) for index, (key, label) in enumerate(checks, start=1) if dataset[key] in {"", "missing", "unknown"}]
