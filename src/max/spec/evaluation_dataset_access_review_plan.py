"""Generate deterministic evaluation dataset access review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.evaluation_dataset_access_review_plan.v1"
KIND = "max.spec.evaluation_dataset_access_review_plan"


def generate_evaluation_dataset_access_review_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "evaluation_dataset_access_review")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    datasets = unique_records(
        named(
            hints.get("datasets") or hints.get("dataset_inventory") or hints.get("evaluation_datasets"),
            ("dataset", "source", "classification"),
        ),
        [
            {
                "name": "sensitive evaluation dataset",
                "dataset": "sensitive evaluation dataset",
                "classification": "restricted",
                "owner": "evaluation_owner",
            }
        ],
    )
    access_entries = unique_records(
        _named_access(hints.get("access_entries") or hints.get("access") or hints.get("roles")),
        [{"name": "sensitive evaluation dataset / reviewer", "dataset": "sensitive evaluation dataset", "role": "reviewer"}],
    )
    grouped_access = _group_access(access_entries, evidence_ids)
    access_risks = _access_risks(access_entries, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Evaluation Dataset Access Review Plan",
        "summary": source_summary(
            ctx,
            dataset_count=len(datasets),
            access_group_count=len(grouped_access),
            access_risk_count=len(access_risks),
        ),
        "dataset_inventory": [
            item(
                "EDA",
                index,
                record,
                "evaluation_owner",
                evidence_ids,
                "Inventory sensitive evaluation dataset",
                name_keys=("name", "dataset", "source"),
                extra_keys=("dataset", "source", "classification"),
            )
            for index, record in enumerate(datasets, start=1)
        ],
        "access_by_dataset_role": grouped_access,
        "approval_evidence": section(
            hints,
            ("approval_evidence", "approvals", "approval_records"),
            "EDE",
            "security_owner",
            "Verify dataset access approval evidence",
            evidence_ids,
            ["manager approval, data owner approval, ticket reference, and expiration date"],
        ),
        "access_risks": access_risks,
        "least_privilege_actions": section(
            hints,
            ("least_privilege_actions", "least_privilege", "privilege_actions"),
            "EDL",
            "security_owner",
            "Apply dataset least privilege action",
            evidence_ids,
            ["downgrade excessive access, split reviewer role, remove dormant principals, and require break-glass approval"],
        ),
        "revocation_schedule": section(
            hints,
            ("revocation_schedule", "revocations", "revocation"),
            "EDR",
            "security_owner",
            "Schedule dataset access revocation",
            evidence_ids,
            ["revoke expired approvals, remove project-complete access, and confirm emergency access expiry"],
        ),
        "monitoring_tasks": section(
            hints,
            ("monitoring_tasks", "monitoring", "audit_tasks"),
            "EDM",
            "security_owner",
            "Monitor evaluation dataset access",
            evidence_ids,
            ["log reads, alert on bulk export, review failed access attempts, and archive recertification evidence"],
        ),
        "recertification_checkpoints": section(
            hints,
            ("recertification_checkpoints", "recertification", "checkpoints"),
            "EDC",
            "program_owner",
            "Recertify evaluation dataset access",
            evidence_ids,
            ["data owner recertification, stale approval closure, revocation proof, and monitoring review"],
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _group_access(records: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        dataset = compact(record.get("dataset")) or "sensitive evaluation dataset"
        role = compact(record.get("role")) or "reviewer"
        key = (dataset.casefold(), role.casefold())
        group = groups.setdefault(
            key,
            {
                "dataset": dataset,
                "role": role,
                "principals": [],
                "privileges": [],
                "approval_statuses": [],
                "owner": compact(record.get("owner")),
            },
        )
        for source, target in (
            ("principal", "principals"),
            ("user", "principals"),
            ("group", "principals"),
            ("privilege", "privileges"),
            ("permission", "privileges"),
            ("approval_status", "approval_statuses"),
            ("status", "approval_statuses"),
        ):
            value = compact(record.get(source))
            if value and value not in group[target]:
                group[target].append(value)
        if not group["owner"] and compact(record.get("owner")):
            group["owner"] = compact(record.get("owner"))

    rows = []
    for index, group in enumerate(
        sorted(groups.values(), key=lambda item: (item["dataset"].casefold(), item["role"].casefold())),
        start=1,
    ):
        rows.append(
            row(
                "EDG",
                index,
                f"{group['dataset']} / {group['role']}",
                group["owner"] or "security_owner",
                f"Review {group['role']} access to {group['dataset']}.",
                evidence_ids,
                severity="medium",
                dataset=group["dataset"],
                role=group["role"],
                principals=", ".join(group["principals"]),
                privileges=", ".join(group["privileges"]),
                approval_status=", ".join(group["approval_statuses"]),
            )
        )
    return rows


def _named_access(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    result = []
    for record in value:
        if not isinstance(record, dict) or compact(record.get("name")):
            result.append(record)
            continue
        dataset = compact(record.get("dataset")) or "sensitive evaluation dataset"
        role = compact(record.get("role")) or "reviewer"
        principal = compact(record.get("principal") or record.get("user") or record.get("group"))
        name = f"{dataset} / {role}" + (f" / {principal}" if principal else "")
        result.append({**record, "name": name})
    return result


def _access_risks(records: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for record in records:
        dataset = compact(record.get("dataset")) or "sensitive evaluation dataset"
        role = compact(record.get("role")) or "reviewer"
        status = compact(record.get("approval_status") or record.get("status")).lower()
        privilege = compact(record.get("privilege") or record.get("permission")).lower()
        owner = compact(record.get("owner"))
        if any(term in status for term in ("stale", "expired", "missing", "overdue")):
            risks.append(_risk(len(risks) + 1, dataset, role, "stale approval", "Refresh or revoke access with stale approval evidence.", evidence_ids))
        if any(term in privilege for term in ("admin", "owner", "write", "all", "excessive")):
            risks.append(_risk(len(risks) + 1, dataset, role, "excessive privilege", "Downgrade access to the minimum role required for evaluation work.", evidence_ids))
        if not owner:
            risks.append(_risk(len(risks) + 1, dataset, role, "missing owner", "Assign a dataset or access owner before recertification closes.", evidence_ids))
    return risks


def _risk(
    index: int,
    dataset: str,
    role: str,
    gap: str,
    description: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return row(
        "EDX",
        index,
        f"{gap}: {dataset} / {role}",
        "security_owner",
        description,
        evidence_ids,
        severity="high",
        dataset=dataset,
        role=role,
        gap=gap,
    )
