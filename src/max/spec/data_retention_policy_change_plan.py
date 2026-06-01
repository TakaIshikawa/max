"""Generate deterministic data retention policy change plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.data_retention_policy_change_plan.v1"
KIND = "max.spec.data_retention_policy_change_plan"


def generate_data_retention_policy_change_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    dataset = _required(hints, "dataset", "dataset")
    current = _required(hints, "current_retention", "current retention")
    proposed = _required(hints, "proposed_retention", "proposed retention")
    legal_basis = _required(hints, "legal_basis", "legal basis")
    systems = _required_list(hints.get("affected_systems"), "affected systems")
    owners = _required_list(hints.get("owners"), "owners")
    deadline = compact(hints.get("migration_deadline")) or "migration deadline not set"
    channels = _required_list(hints.get("communication_channels"), "communication channels")
    direction = _direction(current, proposed)
    refs = [item["id"] for item in ctx["evidence_references"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, dataset=dataset, current_retention=current, proposed_retention=proposed, change_type=direction, migration_deadline=deadline),
        "impact_analysis": [_row("DRI", 1, dataset, owners[0], f"Assess {direction} retention change from {current} to {proposed} under {legal_basis}.", refs, legal_basis=legal_basis)],
        "migration_tasks": [_row("DRM", i, system, owners[(i - 1) % len(owners)], f"Update {system} retention controls for {dataset} by {deadline}.", refs, current_retention=current, proposed_retention=proposed) for i, system in enumerate(systems, 1)],
        "deletion_verification": [_row("DRV", i, system, owners[(i - 1) % len(owners)], f"Verify expired {dataset} records are deleted or preserved according to {proposed}.", refs, required_when="shorter retention" if direction == "shorter" else "policy reconciliation") for i, system in enumerate(systems, 1)],
        "stakeholder_communication": [_row("DRC", i, channel, owners[(i - 1) % len(owners)], f"Communicate {dataset} retention policy change through {channel}.", refs, deadline=deadline) for i, channel in enumerate(channels, 1)],
        "rollback_criteria": [_row("DRB", 1, "Retention rollback criteria", owners[0], "Rollback if deletion verification fails, legal basis changes, or an affected system cannot enforce the proposed retention.", refs)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("data_retention_policy_change")
    return value if isinstance(value, dict) else {}


def _required(hints: dict[str, Any], key: str, label: str) -> str:
    value = compact(hints.get(key))
    if not value or hints.get(key) in ([], {}):
        raise ValueError(f"data_retention_policy_change requires {label}")
    return value


def _required_list(value: Any, label: str) -> list[str]:
    values = sorted(dict.fromkeys(item for item in string_list(value) if item), key=str.casefold)
    if not values:
        raise ValueError(f"data_retention_policy_change requires {label}")
    return values


def _direction(current: str, proposed: str) -> str:
    current_days = _days(current)
    proposed_days = _days(proposed)
    if current_days is not None and proposed_days is not None:
        return "shorter" if proposed_days < current_days else "longer" if proposed_days > current_days else "unchanged"
    return "changed"


def _days(value: str) -> int | None:
    parts = value.lower().split()
    if not parts:
        return None
    try:
        amount = int(parts[0])
    except ValueError:
        return None
    unit = parts[1] if len(parts) > 1 else "days"
    if unit.startswith("year"):
        return amount * 365
    if unit.startswith("month"):
        return amount * 30
    return amount


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None)})
    return data
