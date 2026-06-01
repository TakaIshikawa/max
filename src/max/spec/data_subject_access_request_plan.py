"""Data subject access request operational plan generator."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable

SCHEMA_VERSION = "max.spec.data_subject_access_request_plan.v1"
KIND = "max.spec.data_subject_access_request_plan"


def generate_data_subject_access_request_plan(
    request: dict[str, Any],
    systems: Iterable[dict[str, Any]],
    *,
    sla_days: int = 30,
) -> dict[str, Any]:
    subject_id = _text(request.get("subject_id") or request.get("subject") or request.get("data_subject_id"))
    request_id = _text(request.get("request_id") or request.get("id") or request.get("case_id"))
    if not subject_id:
        raise ValueError("subject_id is required")
    if not request_id:
        raise ValueError("request_id is required")

    received_on = _date_text(request.get("received_on") or request.get("received_at") or request.get("received_date"))
    deadline = _deadline(received_on, sla_days)
    system_rows = [_system(row, index) for index, row in enumerate(systems, start=1)]
    system_rows.sort(key=lambda row: (row["owner"].casefold(), row["system"].casefold()))

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in system_rows:
        grouped.setdefault(row["owner"], []).append(row)

    milestones = [
        {"id": "M1", "name": "Intake complete", "owner": "privacy_owner", "due": received_on or "at intake"},
        {"id": "M2", "name": "Identity verified", "owner": "support_owner", "due": "within 5 days"},
        {"id": "M3", "name": "Data discovery complete", "owner": "data_owner", "due": "before review"},
        {"id": "M4", "name": "Response delivered", "owner": "privacy_owner", "due": deadline or f"{sla_days} days from receipt"},
    ]
    tasks = _tasks(system_rows, deadline)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": f"DSAR Plan {request_id}",
        "summary": {
            "request_id": request_id,
            "subject_id": subject_id,
            "request_type": _text(request.get("request_type") or request.get("type")) or "access",
            "received_on": received_on,
            "sla_days": max(0, int(sla_days)),
            "deadline": deadline,
            "system_count": len(system_rows),
        },
        "owners": _owners(system_rows),
        "systems_by_owner": [{"owner": owner, "systems": rows} for owner, rows in sorted(grouped.items(), key=lambda item: item[0].casefold())],
        "milestones": milestones,
        "tasks": tasks,
        "evidence_checklist": [
            "intake record",
            "identity verification proof",
            "system discovery manifest",
            "export review signoff",
            "delivery receipt",
            "audit closure note",
        ],
    }


def _tasks(systems: list[dict[str, Any]], deadline: str) -> list[dict[str, Any]]:
    tasks = [
        {"id": "T1", "phase": "intake", "owner": "privacy_owner", "task": "Log DSAR scope, jurisdiction, request type, and communication channel.", "due": "same business day"},
        {"id": "T2", "phase": "identity_verification", "owner": "support_owner", "task": "Verify requester identity and authorization before disclosure.", "due": "within 5 days"},
        {"id": "T3", "phase": "data_discovery", "owner": "data_owner", "task": "Confirm responsive systems and collection owners.", "due": "before export review"},
    ]
    for index, system in enumerate(systems, start=1):
        tasks.append(
            {
                "id": f"T{index + 3}",
                "phase": "data_discovery",
                "owner": system["owner"],
                "task": f"Extract and review responsive data from {system['system']}.",
                "due": "before export review",
                "system": system["system"],
            }
        )
    offset = len(tasks)
    tasks.extend(
        [
            {"id": f"T{offset + 1}", "phase": "export_review", "owner": "privacy_owner", "task": "Review export for exemptions, redactions, and third-party data.", "due": "before delivery"},
            {"id": f"T{offset + 2}", "phase": "delivery", "owner": "privacy_owner", "task": "Deliver response through an approved secure channel.", "due": deadline or "by SLA deadline"},
            {"id": f"T{offset + 3}", "phase": "audit_evidence", "owner": "privacy_owner", "task": "Archive evidence, approvals, delivery proof, and closure notes.", "due": "at closure"},
        ]
    )
    return tasks


def _system(raw: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "system": _text(raw.get("system") or raw.get("name") or raw.get("source")) or f"system-{index}",
        "owner": _text(raw.get("owner") or raw.get("team")) or "data_owner",
        "data_categories": _items(raw.get("data_categories") or raw.get("categories")),
        "export_method": _text(raw.get("export_method") or raw.get("method")) or "audited export",
    }


def _owners(systems: list[dict[str, Any]]) -> list[dict[str, str]]:
    owners = {
        "privacy_owner": "Own DSAR policy, response review, delivery, and closure evidence.",
        "support_owner": "Own intake communications and identity verification.",
        "data_owner": "Own data discovery and system extraction coordination.",
    }
    for system in systems:
        owners.setdefault(system["owner"], f"Own discovery and extraction for {system['system']}.")
    return [{"owner": owner, "responsibility": responsibility} for owner, responsibility in sorted(owners.items(), key=lambda item: item[0].casefold())]


def _deadline(received_on: str, sla_days: int) -> str:
    if not received_on:
        return ""
    try:
        return (date.fromisoformat(received_on) + timedelta(days=max(0, int(sla_days)))).isoformat()
    except ValueError:
        return ""


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _text(value)


def _items(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(";", ",").split(",")
    elif isinstance(value, Iterable):
        raw = list(value)
    else:
        raw = []
    return sorted({_text(item) for item in raw if _text(item)}, key=str.casefold)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
