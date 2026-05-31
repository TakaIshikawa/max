"""Generate deterministic evaluation dataset consent audit plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.evaluation_dataset_consent_audit_plan.v1"
KIND = "max.spec.evaluation_dataset_consent_audit_plan"


def generate_evaluation_dataset_consent_audit_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "evaluation_dataset_consent_audit")
    datasets = _datasets(hints)
    groups = _groups(datasets, evidence_ids)
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Evaluation Dataset Consent Audit Plan", "summary": source_summary(ctx, dataset_count=len(datasets), consent_group_count=len(groups)), "audit_scope": [item("EDA", i, row, "data_owner", evidence_ids, "Audit evaluation dataset consent", extra_keys=("consent_status", "provenance", "sensitive_category")) for i, row in enumerate(datasets, 1)], "consent_status_groups": groups, "evidence_needed": section(hints, ("evidence_needed", "evidence", "proof"), "EDE", "data_owner", "Collect consent audit evidence", evidence_ids, ["consent basis, dataset provenance, revocation log, and sensitive category review"]), "remediation_actions": _remediation(datasets, evidence_ids), "accountable_owner": section(hints, ("accountable_owner", "owners", "approvers"), "EDO", "data_owner", "Assign consent audit owner", evidence_ids, ["data owner and evaluation owner approve remediation before dataset use"]), "completion_criteria": section(hints, ("completion_criteria", "criteria"), "EDC", "data_owner", "Complete consent audit", evidence_ids, ["all datasets have valid consent basis, provenance, revocation handling, and evidence references"]), "evidence_references": ctx["evidence_references"]}


def _datasets(hints: dict[str, Any]) -> list[dict[str, Any]]:
    rows = unique_records(named(hints.get("datasets") or hints.get("dataset_entries"), ("dataset", "name")), [{"name": "evaluation dataset inventory bootstrap", "consent_status": "unknown", "provenance": "missing"}])
    return sorted(({**row, "consent_status": compact(row.get("consent_status") or row.get("consent") or "unknown"), "provenance": compact(row.get("provenance") or row.get("source") or "missing")} for row in rows), key=lambda row: (_rank(row), compact(row.get("name")).casefold()))


def _groups(datasets: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    statuses = sorted({row["consent_status"] for row in datasets}, key=str.casefold)
    return [item("EDG", i, {"name": status, "description": f"Review {sum(1 for row in datasets if row['consent_status'] == status)} dataset(s) with {status} consent status."}, "data_owner", evidence_ids, "Group datasets by consent status") for i, status in enumerate(statuses, 1)]


def _remediation(datasets: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    actions = []
    for row in datasets:
        status = row["consent_status"].lower()
        if "revoked" in status:
            description = "Remove revoked records from evaluation sets, quarantine derived labels, and capture revocation evidence."
        elif "missing" in row["provenance"].lower() or row["provenance"].lower() == "missing":
            description = "Block dataset use until provenance, collection source, and consent basis are attached."
        elif status in {"missing", "unknown", "noncompliant"}:
            description = "Collect consent basis or replace the dataset before evaluation use."
        else:
            description = "Retain consent evidence and include dataset in audit sampling."
        actions.append(item("EDR", len(actions) + 1, {"name": row["name"], "description": description, "severity": "high" if "Block" in description or "Remove" in description else "low"}, "data_owner", evidence_ids, "Remediate consent audit gap"))
    return actions


def _rank(row: dict[str, Any]) -> int:
    text = f"{row['consent_status']} {row['provenance']}".lower()
    if "revoked" in text:
        return 0
    if "missing" in text or "unknown" in text or "noncompliant" in text:
        return 1
    return 2
