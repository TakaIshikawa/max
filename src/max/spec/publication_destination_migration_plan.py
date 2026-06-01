"""Generate publication destination migration plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, summary

SCHEMA_VERSION = "max.spec.publication_destination_migration_plan.v1"
KIND = "max.spec.publication_destination_migration_plan"


def generate_publication_destination_migration_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    rows = _destinations(spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, destination_count=len(rows), wave_count=len(rows)),
        "source_inventory": [{"destination": row["source_destination"], "auth_mode": row["source_auth_mode"]} for row in rows],
        "destination_inventory": [{"destination": row["target_destination"], "auth_mode": row["target_auth_mode"]} for row in rows],
        "migration_waves": sorted(rows, key=lambda row: (row["planned_at"], row["target_destination"].casefold())),
        "payload_mapping_checks": _checks(rows),
        "rollback_steps": [{"id": f"RB{idx}", "destination": row["target_destination"], "action": "Restore publisher routing to the source destination and replay failed publication attempts."} for idx, row in enumerate(rows, start=1)],
        "validation_gates": [{"id": "VG1", "name": "dual_publish_verified"}, {"id": "VG2", "name": "webhook_delivery_verified"}],
        "evidence_references": ctx["evidence_references"],
    }


def _destinations(spec: dict[str, Any]) -> list[dict[str, str]]:
    raw = spec.get("destinations") or spec.get("migration_waves") or spec.get("rows") or []
    rows = []
    for index, item in enumerate(raw if isinstance(raw, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        rows.append({"id": compact(item.get("id")) or f"W{index}", "source_destination": compact(item.get("source_destination") or item.get("source")) or "current", "target_destination": compact(item.get("target_destination") or item.get("destination") or item.get("target")) or f"destination_{index}", "planned_at": compact(item.get("planned_at")) or "", "source_auth_mode": compact(item.get("source_auth_mode")) or "existing", "target_auth_mode": compact(item.get("target_auth_mode")) or "managed_secret", "owner": compact(item.get("owner")) or "publishing_owner"})
    return rows


def _checks(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    names = ("authentication", "field_mapping", "quota", "webhook_delivery")
    return [{"id": f"PMC{idx}", "destination": row["target_destination"], "check": name, "status": "required"} for row in rows for idx, name in enumerate(names, start=1)]
