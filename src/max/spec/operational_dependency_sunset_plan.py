"""Generate deterministic operational dependency sunset plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.operational_dependency_sunset_plan.v1"
KIND = "max.spec.operational_dependency_sunset_plan"


def generate_operational_dependency_sunset_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "operational_dependency_sunset")
    dependencies = unique_records(
        _named(hints.get("dependencies"), ("dependency",)),
        [
            {
                "name": "operational dependency sunset",
                "owner": "operations_owner",
                "severity": "medium",
                "deadline_status": "missing",
            }
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, dependency_count=len(dependencies)),
        "dependency_sunsets": [_item("ODS", index, item, "operations_owner", evidence_ids) for index, item in enumerate(dependencies, start=1)],
        "consumers": _section(hints, ("consumers", "affected_consumers"), "ODC", "consumer_owner", "Confirm affected consumer", evidence_ids, ["consumer inventory"]),
        "replacement_paths": _section(hints, ("replacement_path", "replacement_paths"), "ODR", "replacement_owner", "Track replacement path", evidence_ids, ["replacement dependency plan"]),
        "risk_controls": _section(hints, ("risks", "risk_controls", "controls"), "ODK", "risk_owner", "Operate risk control", evidence_ids, ["sunset risk control"]),
        "owner_handoffs": _section(hints, ("owners", "owner_handoffs"), "ODO", "operations_owner", "Complete owner handoff", evidence_ids, ["owner handoff record"]),
        "communications": _section(hints, ("communications", "notices"), "ODM", "communications_owner", "Send sunset communication", evidence_ids, ["consumer communication"]),
        "rollback_criteria": _section(hints, ("rollback", "rollback_criteria"), "ODB", "operations_owner", "Define rollback criteria", evidence_ids, ["dependency rollback path"]),
        "evidence_references": ctx["evidence_references"],
    }


def _section(hints: dict[str, Any], keys: tuple[str, ...], prefix: str, owner: str, label: str, evidence_ids: list[str], fallback: list[Any]) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return [_item(prefix, index, item, owner, evidence_ids, label) for index, item in enumerate(unique_records(value, fallback), start=1)]


def _item(prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str], label: str = "Review operational dependency sunset") -> dict[str, Any]:
    name = compact(item.get("name") or item.get("dependency"))
    return row(prefix, index, name, compact(item.get("owner")) or owner, compact(item.get("description")) or f"{label}: {name}.", evidence_ids, severity=compact(item.get("severity")) or "medium", status=compact(item.get("status") or item.get("deadline_status")) or "open", deadline=compact(item.get("deadline") or item.get("due")), consumer=compact(item.get("consumer")))


def _named(value: Any, aliases: tuple[str, ...]) -> Any:
    if not isinstance(value, list):
        return value
    result = []
    for item in value:
        if isinstance(item, dict) and not compact(item.get("name")):
            item = {**item, "name": next((compact(item.get(key)) for key in aliases if compact(item.get(key))), "")}
        result.append(item)
    return result
