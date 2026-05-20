"""Generate deterministic audit readiness gap plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.audit_readiness_gap_plan.v1"
KIND = "max.spec.audit_readiness_gap_plan"


def generate_audit_readiness_gap_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    required = _evidence_items(hints.get("required_evidence") or hints.get("evidence"))
    existing = set(item.casefold() for item in string_list(hints.get("existing_evidence") or hints.get("available_evidence")))
    if not required:
        required = [{"control": "launch control", "evidence": "approval record", "owner": "compliance_owner"}]
    gaps = [item for item in required if item["evidence"].casefold() not in existing]
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, required_evidence_count=len(required), evidence_gap_count=len(gaps), audit_deadline=compact(hints.get("audit_deadline") or hints.get("deadline")) or "before audit"),
        "audit_scope": _scope(hints, ctx, evidence_ids),
        "required_evidence": [_required(index, item, evidence_ids) for index, item in enumerate(required, start=1)],
        "evidence_gaps": [_gap(index, item, evidence_ids) for index, item in enumerate(gaps, start=1)],
        "remediation_actions": [_remediation(index, item, evidence_ids) for index, item in enumerate(gaps, start=1)],
        "auditor_questions": _questions(hints, required, evidence_ids),
        "signoffs": _signoffs(hints, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _scope(hints: dict[str, Any], ctx: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    controls = string_list(hints.get("controls") or hints.get("audit_scope")) or ["change approval", "evidence retention", ctx["workflow_context"]]
    return [{"id": f"SC{index}", "control": control, "owner": compact(hints.get("owner")) or "compliance_owner", "evidence_reference_ids": evidence_ids} for index, control in enumerate(sorted(controls, key=str.casefold), start=1)]


def _required(index: int, item: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"RE{index}", **item, "evidence_reference_ids": evidence_ids}


def _gap(index: int, item: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"EG{index}", "control": item["control"], "missing_evidence": item["evidence"], "owner": item["owner"], "evidence_reference_ids": evidence_ids}


def _remediation(index: int, item: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"RA{index}", "action": f"Collect and attach {item['evidence']} for {item['control']}.", "owner": item["owner"], "due": "before audit", "evidence_reference_ids": evidence_ids}


def _questions(hints: dict[str, Any], required: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    questions = string_list(hints.get("auditor_questions")) or [f"Where is the evidence for {item['control']}?" for item in required]
    return [{"id": f"AQ{index}", "question": question, "owner": "compliance_owner", "evidence_reference_ids": evidence_ids} for index, question in enumerate(questions, start=1)]


def _signoffs(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    roles = string_list(hints.get("signoffs") or hints.get("approvers")) or ["compliance_owner", "control_owner"]
    return [{"id": f"SO{index}", "role": role, "status": "pending", "evidence_reference_ids": evidence_ids} for index, role in enumerate(sorted(roles, key=str.casefold), start=1)]


def _evidence_items(value: Any) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append({"control": compact(item.get("control") or item.get("name")) or f"control {index}", "evidence": compact(item.get("evidence") or item.get("required_evidence")) or f"evidence {index}", "owner": compact(item.get("owner")) or "control_owner"})
        else:
            text = compact(item) or f"evidence {index}"
            rows.append({"control": text, "evidence": text, "owner": "control_owner"})
    return sorted(rows, key=lambda row: (row["control"].casefold(), row["evidence"].casefold()))


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("audit_readiness_gap")
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
