"""Generate deterministic compliance evidence retention plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.compliance_evidence_retention_plan.v1"
KIND = "max.spec.compliance_evidence_retention_plan"


def generate_compliance_evidence_retention_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    frameworks = _values(hints.get("frameworks"), ["SOC 2"])
    evidence_types = _values(hints.get("evidence_types"), ["approval records", "control test results", "system exports"])
    retention_period = compact(hints.get("retention_period")) or "7 years"
    storage = compact(hints.get("storage_location")) or "access-controlled evidence repository"
    legal_hold = _truthy(hints.get("legal_hold"))
    restricted = _truthy(hints.get("restricted_access"))
    strict = legal_hold or restricted or ctx["strictness"] == "strict"
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, frameworks=frameworks, retention_period=retention_period, legal_hold=legal_hold, restricted_access=restricted),
        "retention_policy": [
            _item("RP1", "retention_period", "compliance_owner", f"Retain compliance evidence for {retention_period}.", "high" if strict else "medium", evidence_ids=evidence_ids),
            _item("RP2", "framework_scope", "compliance_owner", f"Apply retention policy to {', '.join(frameworks)} evidence.", "medium", evidence_ids=evidence_ids),
        ],
        "evidence_categories": [_item(f"EC{index}", value, "control_owner", f"Classify and retain {value}.", "medium", evidence_ids=evidence_ids) for index, value in enumerate(evidence_types, start=1)],
        "storage_controls": [
            _item("SC1", "central_repository", "compliance_owner", f"Store evidence in {storage}.", "high" if strict else "medium", evidence_ids=evidence_ids),
            _item("SC2", "immutability", "security_owner", "Enable immutable storage or tamper-evident logging for retained evidence.", "high" if strict else "medium", evidence_ids=evidence_ids),
        ],
        "access_controls": [
            _item("AC1", "least_privilege", "security_owner", "Restrict access to named compliance, legal, and control owners." if restricted else "Limit write access to evidence owners and reviewers.", "high" if restricted else "medium", evidence_ids=evidence_ids),
            _item("AC2", "access_review", "security_owner", "Review evidence repository access monthly." if strict else "Review evidence repository access quarterly.", "high" if strict else "medium", evidence_ids=evidence_ids),
        ],
        "review_cadence": [_item("RC1", "retention_review", "compliance_owner", "Review retention coverage quarterly and before each audit.", "medium", evidence_ids=evidence_ids)],
        "disposal_workflow": _disposal_workflow(legal_hold, strict, evidence_ids),
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _disposal_workflow(legal_hold: bool, strict: bool, evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        _item("DW1", "disposal_eligibility", "compliance_owner", "Confirm retention period has elapsed and no open audit depends on the evidence.", "high" if strict else "medium", evidence_ids=evidence_ids),
        _item("DW2", "legal_hold_check", "legal_owner", "Block disposal while legal hold is active and require legal release before deletion." if legal_hold else "Check for legal hold before disposal.", "critical" if legal_hold else "medium", evidence_ids=evidence_ids),
        _item("DW3", "disposal_evidence", "compliance_owner", "Record deletion approval, actor, date, and evidence identifiers.", "high" if strict else "medium", evidence_ids=evidence_ids),
    ]


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "compliance_owner", "suggested_owner": ctx["buyer"], "responsibility": "Own retention policy, audit readiness, and disposal approvals."},
        {"role": "control_owner", "suggested_owner": "control_owner", "responsibility": "Provide complete evidence categories on schedule."},
        {"role": "security_owner", "suggested_owner": "security_owner", "responsibility": "Own storage, access controls, and access reviews."},
        {"role": "legal_owner", "suggested_owner": "legal_owner", "responsibility": "Approve legal hold and release decisions."},
    ]


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("compliance_evidence_retention")
    return hints if isinstance(hints, dict) else {}


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _truthy(value: Any) -> bool:
    return value is True or compact(value).lower() in {"1", "true", "yes", "y", "required", "restricted"}


def _item(item_id: str, name: str, owner: str, description: str, severity: str, *, evidence_ids: list[str] | None = None) -> dict[str, Any]:
    return {"id": item_id, "name": name, "owner": owner, "severity": severity, "description": description, "evidence_reference_ids": evidence_ids or []}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
