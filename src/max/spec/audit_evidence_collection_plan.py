"""Generate deterministic audit evidence collection plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.audit_evidence_collection_plan.v1"
KIND = "max.spec.audit_evidence_collection_plan"


def generate_audit_evidence_collection_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    frameworks = _values(hints.get("frameworks"), ["SOC 2"])
    controls = _values(hints.get("controls"), ["access review", "change management"])
    systems = _values(hints.get("systems"), ["production systems"])
    evidence_types = _values(hints.get("evidence_types"), ["system export", "approval record"])
    cadence = compact(hints.get("cadence")) or "quarterly"
    reviewers = _values(hints.get("reviewers"), ["control_owner", "compliance_owner"])
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, frameworks=frameworks, control_count=len(controls), collection_cadence=cadence),
        "evidence_scope": [
            _item("ES1", "framework_scope", "compliance_owner", f"Collect evidence for {', '.join(frameworks)}.", "medium", evidence_ids=evidence_ids),
            _item("ES2", "system_scope", "control_owner", f"Systems in scope: {', '.join(systems)}.", "medium", evidence_ids=evidence_ids),
        ],
        "collection_tasks": _collection_tasks(controls, evidence_types, cadence, evidence_ids),
        "control_mapping": [_item(f"CM{index}", control, "control_owner", f"Map {control} to {', '.join(frameworks)} evidence requests.", "medium", references=frameworks, evidence_ids=evidence_ids) for index, control in enumerate(controls, start=1)],
        "retention_rules": [
            _item("RR1", "evidence_retention", "compliance_owner", "Retain collected evidence for the audit retention period with immutable timestamps.", "medium", evidence_ids=evidence_ids),
            _item("RR2", "source_traceability", "compliance_owner", "Preserve source system, query, collector, and collection date for each artifact.", "medium", evidence_ids=evidence_ids),
        ],
        "reviewer_workflow": [_item(f"RW{index}", reviewer, reviewer, f"{reviewer} reviews completeness and approves evidence readiness.", "medium", evidence_ids=evidence_ids) for index, reviewer in enumerate(reviewers, start=1)],
        "gaps_and_remediation": [
            _item("GR1", "missing_evidence", "control_owner", "Open remediation task for missing, stale, or mismatched evidence.", "high" if ctx["strictness"] == "strict" else "medium", evidence_ids=evidence_ids),
            _item("GR2", "auditor_question_followup", "compliance_owner", "Track auditor questions to owner, due date, and final response evidence.", "medium", evidence_ids=evidence_ids),
        ],
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _collection_tasks(controls: list[str], evidence_types: list[str], cadence: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for control in controls:
        for evidence_type in evidence_types:
            tasks.append(_item(f"CT{len(tasks) + 1}", f"{control} {evidence_type}", "control_owner", f"Collect {evidence_type} for {control} every {cadence}.", "medium", evidence_ids=evidence_ids))
    return tasks


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "compliance_owner", "suggested_owner": ctx["buyer"], "responsibility": "Own audit scope, collection calendar, and auditor responses."},
        {"role": "control_owner", "suggested_owner": "control_owner", "responsibility": "Collect control evidence and remediate gaps."},
        {"role": "reviewer", "suggested_owner": "reviewer", "responsibility": "Approve evidence completeness and traceability."},
    ]


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("audit_evidence")
    return hints if isinstance(hints, dict) else {}


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _item(
    item_id: str,
    name: str,
    owner: str,
    description: str,
    severity: str,
    *,
    references: list[str] | None = None,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {"id": item_id, "name": name, "owner": owner, "severity": severity, "description": description, "references": references or [], "evidence_reference_ids": evidence_ids or []}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
