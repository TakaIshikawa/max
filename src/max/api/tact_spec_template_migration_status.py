"""JSON API renderer for tact spec template migration status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.tact_spec_template_migration_status.v1"
KIND = "max.api.tact_spec_template_migration_status"


def tact_spec_template_migration_status_to_json(payload: Mapping[str, Any]) -> str:
    target = _text(payload.get("target_template_version") or payload.get("target_version") or "current")
    specs = [_spec(row, i, target) for i, row in enumerate(list_of_maps(payload.get("specs") or payload.get("rows")), start=1)]
    status = "blocked" if any(row["status"] == "blocked" for row in specs) else ("not_ready" if any(row["status"] == "not_ready" for row in specs) else "ready")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "readiness_status": status, "target_template_version": target, "total_specs": len(specs), "migrated_count": sum(1 for row in specs if row["migrated"]), "incompatible_count": sum(1 for row in specs if row["incompatible"]), "validation_failure_count": sum(len(row["validation_failures"]) for row in specs), "rollback_blocker_count": sum(len(row["rollback_blockers"]) for row in specs), "failure_buckets": _buckets(specs), "next_actions": _actions(specs), "specs": sorted(specs, key=lambda row: (row["status"], row["spec_id"].casefold())), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _spec(item: Mapping[str, Any], index: int, target: str) -> dict[str, Any]:
    version = _text(item.get("template_version") or item.get("version"))
    failures = strings(item.get("validation_failures") or item.get("failures"))
    blockers = strings(item.get("rollback_blockers"))
    incompatible = bool(item.get("incompatible") or item.get("incompatible_with_target"))
    migrated = version == target and not failures and not blockers and not incompatible
    status = "blocked" if blockers or incompatible else ("not_ready" if failures or not migrated else "ready")
    return {"spec_id": _text(item.get("spec_id") or item.get("id")) or f"spec-{index}", "template_version": version or "unknown", "target_template_version": target, "migrated": migrated, "incompatible": incompatible, "validation_failures": failures, "rollback_blockers": blockers, "status": status, "recommended_action": "clear rollback blockers" if blockers else ("resolve template incompatibility" if incompatible else ("fix validation failures" if failures else ("migrate spec to target template" if not migrated else "continue monitoring")))}


def _buckets(specs: list[Mapping[str, Any]]) -> dict[str, int]:
    return {"incompatible": sum(1 for row in specs if row["incompatible"]), "validation_failures": sum(1 for row in specs if row["validation_failures"]), "rollback_blockers": sum(1 for row in specs if row["rollback_blockers"])}


def _actions(specs: list[Mapping[str, Any]]) -> list[str]:
    actions = []
    if any(row["rollback_blockers"] for row in specs):
        actions.append("clear rollback blockers")
    if any(row["incompatible"] for row in specs):
        actions.append("resolve incompatible specs")
    if any(row["validation_failures"] for row in specs):
        actions.append("fix template validation failures")
    if any(not row["migrated"] and row["status"] == "not_ready" for row in specs):
        actions.append("migrate remaining specs")
    return actions or ["migration ready"]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
