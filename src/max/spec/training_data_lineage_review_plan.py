"""Generate deterministic training data lineage review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.training_data_lineage_review_plan.v1"
KIND = "max.spec.training_data_lineage_review_plan"


def generate_training_data_lineage_review_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "training_data_lineage_review")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    datasets = unique_records(
        named(hints.get("datasets") or hints.get("lineage") or hints.get("training_datasets"), ("dataset", "source", "name")),
        [{"name": "training dataset", "owner": "data_governance_owner"}],
    )
    checks = [_dataset("TDL", index, record, evidence_ids) for index, record in enumerate(datasets, start=1)]
    blockers = _lineage_blockers(checks, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Training Data Lineage Review Plan",
        "summary": source_summary(ctx, dataset_count=len(checks), blocker_count=len(blockers)),
        "lineage_checks": checks,
        "provenance_checks": section(hints, ("provenance_checks", "provenance"), "TDP", "data_governance_owner", "Review dataset provenance", evidence_ids, [row["name"] for row in checks]),
        "license_checks": section(hints, ("license_checks", "licenses"), "TDL", "legal_owner", "Review dataset license", evidence_ids, [row["name"] for row in checks]),
        "consent_basis_checks": section(hints, ("consent_basis_checks", "consent"), "TDC", "privacy_owner", "Review dataset consent basis", evidence_ids, [row["name"] for row in checks]),
        "retention_window_checks": section(hints, ("retention_window_checks", "retention"), "TDR", "privacy_owner", "Review dataset retention window", evidence_ids, [row["name"] for row in checks]),
        "redaction_coverage_checks": section(hints, ("redaction_coverage_checks", "redaction"), "TDA", "data_governance_owner", "Review dataset redaction coverage", evidence_ids, [row["name"] for row in checks]),
        "approver_signoff": section(hints, ("approver_signoff", "approvals", "approvers"), "TDS", "approval_owner", "Capture lineage approver signoff", evidence_ids, ["data governance, legal, privacy, and model owner signoff"]),
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _dataset(prefix: str, index: int, record: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    data = item(prefix, index, record, "data_governance_owner", evidence_ids, "Review training data lineage", name_keys=("name", "dataset", "source"), extra_keys=("source", "license", "consent_basis", "retention_window", "redaction_coverage", "evidence_id"))
    if isinstance(record.get("metadata"), dict):
        data["metadata"] = dict(sorted(record["metadata"].items()))
    return data


def _lineage_blockers(checks: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for check in checks:
        for field in ("source", "license", "consent_basis", "owner"):
            if not compact(check.get(field)) or (field == "owner" and check["owner"] == "data_governance_owner"):
                blockers.append(row("TDB", len(blockers) + 1, f"missing {field} for {check['name']}", "data_governance_owner", f"Dataset lineage must include {field} before review signoff.", evidence_ids, severity="high", dataset=check["name"], missing_field=field))
    return blockers
