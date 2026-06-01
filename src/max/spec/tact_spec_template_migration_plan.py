"""Generate Tact spec template migration plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base

SCHEMA_VERSION = "max.spec.tact_spec_template_migration_plan.v1"
KIND = "max.spec.tact_spec_template_migration_plan"


def generate_tact_spec_template_migration_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "tact_spec_template_migration")
    rows = _rows(hints) or _rows(spec)
    inventory = [_inventory(row, i, evidence_ids, hints) for i, row in enumerate(rows, 1)]
    outdated = [row for row in inventory if row["outdated"]]
    repairs = [row for row in inventory if row["incompatible_fields"] or row["missing_fields"]]
    batches = [{"id": f"TSMB{i}", "batch": i, "template_ids": [row["template_id"] for row in outdated[i - 1:i + 2]], "owner": "spec_platform_owner", "evidence_reference_ids": evidence_ids} for i in range(1, len(outdated) + 1, 3)]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": {"template_count": len(inventory), "outdated_count": len(outdated), "repair_count": len(repairs)},
        "template_inventory": inventory,
        "migration_batches": batches,
        "compatibility_repairs": [{"id": f"TSMR{i}", "template_id": row["template_id"], "action": "repair incompatible or missing fields before migration", "fields": row["incompatible_fields"] + row["missing_fields"], "evidence_reference_ids": evidence_ids} for i, row in enumerate(repairs, 1)],
        "validation_plan": [{"id": "TSMV1", "check": "regenerate spec schema checks for migrated templates", "evidence_reference_ids": evidence_ids}],
        "rollback_triggers": [{"id": "TSMT1", "trigger": "schema validation failure or incompatible rendered spec", "evidence_reference_ids": evidence_ids}],
        "verification_gates": [{"id": "TSMG1", "check": "regenerated spec schema checks pass", "evidence_reference_ids": evidence_ids}],
        "evidence_references": ctx["evidence_references"],
    }


def _rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("templates", "specs", "rows"):
        value = source.get(key) if isinstance(source, dict) else None
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _inventory(row: dict[str, Any], index: int, evidence_ids: list[str], hints: dict[str, Any]) -> dict[str, Any]:
    target = compact(hints.get("target_version") or "v2")
    version = compact(row.get("version") or row.get("template_version") or "unknown")
    incompatible = row.get("incompatible_fields") if isinstance(row.get("incompatible_fields"), list) else []
    missing = row.get("missing_fields") if isinstance(row.get("missing_fields"), list) else []
    return {"id": f"TSMI{index}", "template_id": compact(row.get("id") or row.get("template_id") or row.get("name")) or f"template-{index}", "version": version, "target_version": target, "outdated": version != target, "incompatible_fields": [compact(v) for v in incompatible if compact(v)], "missing_fields": [compact(v) for v in missing if compact(v)], "owner": compact(row.get("owner")) or "spec_platform_owner", "evidence_reference_ids": evidence_ids}
