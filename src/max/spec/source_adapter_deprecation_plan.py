"""Generate source adapter deprecation plans."""

from __future__ import annotations

from typing import Any, Mapping


def generate_source_adapter_deprecation_plan(adapter_inventory: Mapping[str, Any]) -> dict[str, Any]:
    adapter = _map(adapter_inventory.get("adapter") or adapter_inventory)
    affected = sorted({_text(item) for item in adapter_inventory.get("affected_profiles", adapter.get("affected_profiles", [])) if _text(item)})
    candidates = sorted({_text(item) for item in adapter_inventory.get("replacement_sources", adapter.get("replacement_sources", [])) if _text(item)})
    if not affected:
        affected = ["unknown"]
    if not candidates:
        candidates = ["unknown"]
    return {"schema_version": "max.source_adapter_deprecation_plan.v1", "kind": "max.source_adapter_deprecation_plan", "adapter_inventory": {"adapter_id": _text(adapter.get("adapter_id") or adapter.get("id") or adapter.get("name")) or "unknown-adapter", "owner": _text(adapter.get("owner")) or "unknown", "status": _text(adapter.get("status")) or "unknown"}, "affected_profiles": affected, "replacement_source_candidates": candidates, "fallback_source_mapping": [{"profile": profile, "fallback_source": candidates[0]} for profile in affected], "migration_steps": [_step("MIG1", "inventory_usage", "Freeze new usage and inventory dependent profiles."), _step("MIG2", "dual_read", "Run replacement source in parallel for sampled signals."), _step("MIG3", "cutover", "Switch profiles after validation gates pass.")], "validation_gates": [_step("VAL1", "payload_contract", "Replacement payload matches required normalized fields."), _step("VAL2", "freshness", "Replacement source meets freshness SLA."), _step("VAL3", "quality", "Signal quality is equal or better than deprecated adapter.")], "rollback_criteria": [_step("RB1", "quality_regression", "Rollback on quality regression or missing required fields."), _step("RB2", "freshness_breach", "Rollback on repeated freshness breaches.")], "unknowns": [name for name, value in {"owner": adapter.get("owner"), "affected_profiles": affected != ["unknown"], "replacement_sources": candidates != ["unknown"]}.items() if not value]}


def _step(step_id: str, name: str, description: str) -> dict[str, str]:
    return {"id": step_id, "name": name, "description": description}


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
