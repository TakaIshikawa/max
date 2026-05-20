"""Generate deterministic access recertification exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.access_recertification_exception_plan.v1"
KIND = "max.spec.access_recertification_exception_plan"


def generate_access_recertification_exception_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    evidence_ids = _evidence_ids(ctx)
    subjects = _values(hints.get("exception_subjects") or hints.get("subjects"), [ctx["target_user"]])
    scopes = _values(hints.get("access_scopes") or hints.get("scopes"), [f"{ctx['workflow_context']} operational access"])
    justifications = _records(hints.get("business_justification") or hints.get("justifications"), "justification", [{"name": "temporary business continuity", "owner": ctx["buyer"], "description": "Maintain required access until recertification can be completed."}])
    controls = _records(hints.get("compensating_controls") or hints.get("controls"), "control", [{"name": "enhanced monitoring", "owner": "security_owner", "description": "Monitor exception usage until expiry."}])
    approvers = _values(hints.get("approvers"), [ctx["buyer"], "security_owner"])
    checks = _records(hints.get("validation_checks"), "check", [{"name": "expiry and approval check", "owner": "security_owner", "description": "Confirm exception has approver, expiry, and compensating control."}])
    cadence = compact(hints.get("review_cadence")) or ("weekly" if ctx["strictness"] == "strict" else "monthly")
    expiry = compact(hints.get("expiry_date") or hints.get("expiry")) or "next recertification cycle"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, review_cadence=cadence, expiry=expiry),
        "exception_subjects": [_named("SUB", index, subject, "access_owner", evidence_ids) for index, subject in enumerate(subjects, start=1)],
        "access_scopes": [_named("SCOPE", index, scope, "access_owner", evidence_ids) for index, scope in enumerate(scopes, start=1)],
        "justifications": [_item("JUS", index, row, evidence_ids) for index, row in enumerate(justifications, start=1)],
        "compensating_controls": [_item("CTRL", index, row, evidence_ids) for index, row in enumerate(controls, start=1)],
        "approvers": [_named("APP", index, approver, "approver", evidence_ids) for index, approver in enumerate(approvers, start=1)],
        "review_cadence": {"cadence": cadence, "expiry": expiry, "owner": "access_owner", "evidence_reference_ids": evidence_ids},
        "validation_checks": [_item("VC", index, row, evidence_ids) for index, row in enumerate(checks, start=1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("access_recertification_exception")
    return hints if isinstance(hints, dict) else {}


def _records(value: Any, default_name: str, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append({"name": compact(item.get("name") or item.get("justification") or item.get("control") or item.get("check")) or f"{default_name} {index}", "owner": compact(item.get("owner")), "description": compact(item.get("description") or item.get("reason"))})
        else:
            rows.append({"name": compact(item) or f"{default_name} {index}", "owner": "", "description": ""})
    return sorted(rows or fallback, key=lambda row: row["name"].casefold())


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _named(prefix: str, index: int, name: str, owner: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": name, "owner": owner, "evidence_reference_ids": evidence_ids}


def _item(prefix: str, index: int, row: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": row["name"], "owner": row["owner"] or "access_owner", "description": row["description"] or row["name"], "evidence_reference_ids": evidence_ids}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
