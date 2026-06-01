"""Generate deterministic backup restore drill plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.backup_restore_drill_plan.v1"
KIND = "max.spec.backup_restore_drill_plan"


def generate_backup_restore_drill_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    system = _required(hints, "system_name", "system name")
    sources = _required_list(hints.get("backup_sources"), "backup sources")
    target = _required(hints, "restore_target", "restore target")
    rpo = _required(hints, "rpo", "RPO")
    rto = _required(hints, "rto", "RTO")
    owners = _required_list(hints.get("owners"), "owners")
    checks = _required_list(hints.get("validation_checks"), "validation checks")
    drill_date = compact(hints.get("drill_date")) or "not scheduled"
    rollback = compact(hints.get("rollback_criteria")) or "rollback if validation fails"
    refs = [item["id"] for item in ctx["evidence_references"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, system_name=system, restore_target=target, drill_date=drill_date, rpo=rpo, rto=rto),
        "pre_drill_preparation": [_row("BRP", i, source, owners[0], f"Confirm backup source {source} is restorable for {system}.", refs) for i, source in enumerate(sources, 1)],
        "restore_execution": [_row("BRE", 1, "Restore execution", owners[0], f"Restore {system} to {target} on {drill_date} within RTO {rto}.", refs)],
        "data_validation": [_row("BRV", i, check, owners[(i - 1) % len(owners)], f"Validate restored data: {check}.", refs) for i, check in enumerate(checks, 1)],
        "incident_criteria": [_row("BRI", 1, "Incident criteria", owners[0], f"Declare incident if RPO {rpo}, RTO {rto}, or validation checks fail.", refs)],
        "cleanup": [_row("BRC", 1, "Cleanup restored environment", owners[0], f"Clean up {target} after evidence capture.", refs, rollback_criteria=rollback)],
        "lessons_learned": [_row("BRL", 1, "Lessons learned", owners[0], "Record drill findings, gaps, and follow-up owners.", refs)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("backup_restore_drill")
    return value if isinstance(value, dict) else {}


def _required(hints: dict[str, Any], key: str, label: str) -> str:
    if hints.get(key) in ([], {}):
        raise ValueError(f"backup_restore_drill requires {label}")
    value = compact(hints.get(key))
    if not value:
        raise ValueError(f"backup_restore_drill requires {label}")
    return value


def _required_list(value: Any, label: str) -> list[str]:
    values = sorted(dict.fromkeys(item for item in string_list(value) if item), key=str.casefold)
    if not values:
        raise ValueError(f"backup_restore_drill requires {label}")
    return values


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None)})
    return data
