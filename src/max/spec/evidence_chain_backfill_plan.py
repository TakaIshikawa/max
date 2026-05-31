"""Generate deterministic evidence chain backfill plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._compact_plan_common import named
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.evidence_chain_backfill_plan.v1"
KIND = "max.spec.evidence_chain_backfill_plan"


def generate_evidence_chain_backfill_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "evidence_chain_backfill")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    issues = _issues(hints.get("missing_evidence") or hints.get("issues") or hints.get("gaps"))
    groups = _groups(issues, evidence_ids)
    manual_review = [issue for issue in issues if issue["repairability"] == "manual_review"]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Evidence Chain Backfill Plan",
        "summary": source_summary(ctx, issue_count=len(issues), manual_review_count=len(manual_review)),
        "issue_groups": groups,
        "lookup_strategy": _lookup_strategy(groups, evidence_ids),
        "repair_order": [_repair_step(index, issue, evidence_ids) for index, issue in enumerate(issues, start=1)],
        "manual_review": [_manual_step(index, issue, evidence_ids) for index, issue in enumerate(manual_review, start=1)],
        "validation_checks": _validation(evidence_ids),
        "acceptance_criteria": _acceptance(evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _issues(value: Any) -> list[dict[str, Any]]:
    fallback = [{"entity_type": "insight", "entity_id": "missing-evidence-item", "severity": "medium", "repairability": "repairable"}]
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(unique_records(named(value, ("entity_id", "artifact_id", "evidence_id", "entity_type")), fallback), start=1):
        entity_type = compact(item.get("entity_type") or item.get("type") or item.get("artifact_type")) or "unknown"
        entity_id = compact(item.get("entity_id") or item.get("id") or item.get("artifact_id") or item.get("name")) or f"entity-{index}"
        repairability = compact(item.get("repairability") or item.get("status")).lower()
        if repairability in {"unrepairable", "manual", "blocked"} or item.get("unrepairable"):
            repairability = "manual_review"
        else:
            repairability = "repairable"
        rows.append(
            {
                "name": f"{entity_type}:{entity_id}",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "severity": compact(item.get("severity")) or "medium",
                "missing_reference": compact(item.get("missing_reference") or item.get("evidence_id")) or "evidence reference",
                "owner": compact(item.get("owner")) or _owner(entity_type),
                "repairability": repairability,
            }
        )
    return sorted(rows, key=lambda item: (_severity_rank(item["severity"]), item["entity_type"].casefold(), item["entity_id"].casefold()))


def _groups(issues: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    keys = sorted({(issue["entity_type"], issue["severity"]) for issue in issues}, key=lambda key: (_severity_rank(key[1]), key[0].casefold()))
    return [
        row(
            "ECB",
            index,
            f"{entity_type} {severity}",
            _owner(entity_type),
            f"Backfill missing evidence for {entity_type} entities with {severity} severity.",
            evidence_ids,
            entity_type=entity_type,
            severity=severity,
            issue_count=sum(1 for issue in issues if issue["entity_type"] == entity_type and issue["severity"] == severity),
        )
        for index, (entity_type, severity) in enumerate(keys, start=1)
    ]


def _lookup_strategy(groups: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    if not groups:
        return [row("ECL", 1, "empty evidence gap review", "evidence_owner", "Confirm no missing evidence rows were supplied before closure.", evidence_ids)]
    return [
        row("ECL", index, group["name"], group["owner"], f"Lookup {group['entity_type']} evidence using source event ids, lineage manifests, audit logs, and prior tact evidence snapshots.", evidence_ids, entity_type=group["entity_type"], severity=group["severity"])
        for index, group in enumerate(groups, start=1)
    ]


def _repair_step(index: int, issue: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    action = "Queue manual reviewer before mutation" if issue["repairability"] == "manual_review" else "Backfill evidence reference and regenerate downstream trace"
    return row("ECR", index, issue["name"], issue["owner"], f"{action} for {issue['entity_type']} {issue['entity_id']} missing {issue['missing_reference']}.", evidence_ids, entity_type=issue["entity_type"], entity_id=issue["entity_id"], severity=issue["severity"], repairability=issue["repairability"])


def _manual_step(index: int, issue: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    return row("ECM", index, issue["name"], issue["owner"], f"Manual review required because {issue['entity_type']} {issue['entity_id']} cannot be safely backfilled from available lookup sources.", evidence_ids, entity_type=issue["entity_type"], entity_id=issue["entity_id"], severity=issue["severity"])


def _validation(evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        row("ECV", 1, "missing evidence query", "evidence_owner", "Query insights and units for null, orphaned, or unresolved evidence references.", evidence_ids),
        row("ECV", 2, "audit trace sample", "audit_owner", "Sample repaired chains and verify lookup source, repair mutation, and reviewer signoff are recorded.", evidence_ids),
    ]


def _acceptance(evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        row("ECA", 1, "repairable gaps backfilled", "evidence_owner", "All repairable missing evidence references are populated and pass audit trace validation.", evidence_ids),
        row("ECA", 2, "unrepairable gaps reviewed", "audit_owner", "Every unrepairable gap has a manual-review owner, rationale, and exception evidence.", evidence_ids),
    ]


def _owner(entity_type: str) -> str:
    return {"insight": "research_owner", "unit": "spec_owner", "buildable_unit": "spec_owner"}.get(entity_type, "evidence_owner")


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "moderate": 2, "low": 3}.get(compact(value).lower(), 4)
