"""Generate deterministic operational ownership transfer plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.operational_ownership_transfer_plan.v1"
KIND = "max.spec.operational_ownership_transfer_plan"


def generate_operational_ownership_transfer_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    evidence_ids = _evidence_ids(ctx)
    source_team = compact(hints.get("source_team")) or "current owning team"
    receiving_team = compact(hints.get("receiving_team")) or "receiving operations team"
    services = _values(hints.get("owned_services") or hints.get("services"), [ctx["workflow_context"]])
    matrix = _records(hints.get("responsibility_matrix") or hints.get("responsibilities"), "responsibility", [{"name": "incident ownership", "owner": receiving_team, "description": "Receiving team owns incident response after acceptance."}])
    sessions = _records(hints.get("knowledge_transfer_sessions") or hints.get("sessions"), "session", [{"name": "runbook walkthrough", "owner": source_team, "description": "Walk through operational runbooks, alerts, dashboards, and escalation paths."}])
    runbooks = _records(hints.get("runbook_updates") or hints.get("runbooks"), "runbook", [{"name": "operational runbook update", "owner": receiving_team, "description": "Update ownership, paging, and support procedures."}])
    windows = _records(hints.get("support_windows") or hints.get("windows"), "window", [{"name": "hypercare support window", "owner": source_team, "description": "Source team shadows initial operations after transfer."}])
    acceptance = _records(hints.get("acceptance_criteria"), "criterion", [{"name": "receiving team acceptance", "owner": receiving_team, "description": "Receiving team confirms runbooks, alerts, and access are ready."}])
    checks = _records(hints.get("validation_checks"), "check", [{"name": "ownership readiness check", "owner": receiving_team, "description": "Validate access, runbooks, dashboards, and escalation contacts."}])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, source_team=source_team, receiving_team=receiving_team),
        "ownership_scope": {"source_team": source_team, "receiving_team": receiving_team, "owned_services": services, "evidence_reference_ids": evidence_ids},
        "responsibility_matrix": [_item("RESP", index, row, evidence_ids) for index, row in enumerate(matrix, start=1)],
        "knowledge_transfer_sessions": [_item("KT", index, row, evidence_ids) for index, row in enumerate(sessions, start=1)],
        "runbook_updates": [_item("RB", index, row, evidence_ids) for index, row in enumerate(runbooks, start=1)],
        "support_windows": [_item("SW", index, row, evidence_ids) for index, row in enumerate(windows, start=1)],
        "acceptance_criteria": [_item("AC", index, row, evidence_ids) for index, row in enumerate(acceptance, start=1)],
        "validation_checks": [_item("VC", index, row, evidence_ids) for index, row in enumerate(checks, start=1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("operational_ownership_transfer")
    return hints if isinstance(hints, dict) else {}


def _records(value: Any, default_name: str, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append({"name": compact(item.get("name") or item.get("responsibility") or item.get("session") or item.get("runbook") or item.get("criterion") or item.get("check")) or f"{default_name} {index}", "owner": compact(item.get("owner")), "description": compact(item.get("description"))})
        else:
            rows.append({"name": compact(item) or f"{default_name} {index}", "owner": "", "description": ""})
    return sorted(rows or fallback, key=lambda row: row["name"].casefold())


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _item(prefix: str, index: int, row: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": row["name"], "owner": row["owner"] or "operations_owner", "description": row["description"] or row["name"], "evidence_reference_ids": evidence_ids}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
