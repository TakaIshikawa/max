"""Generate deterministic prompt rollback plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.prompt_rollback_plan.v1"
KIND = "max.spec.prompt_rollback_plan"


def generate_prompt_rollback_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "prompt_rollback")
    prompts = unique_records(named(hints.get("prompts") or hints.get("prompt_templates"), ("prompt", "template", "name")), [{"name": "prompt pending rollback inventory", "previous_version": "missing"}])
    prompts = sorted(prompts, key=lambda row: (_rank(row), compact(row.get("name")).casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Prompt Rollback Plan", "summary": source_summary(ctx, prompt_count=len(prompts), missing_previous_version_count=sum(1 for row in prompts if not compact(row.get("previous_version")) or compact(row.get("previous_version")).lower() == "missing")), "impacted_prompts": [item("PRP", i, row, "prompt_owner", evidence_ids, "Inventory impacted prompt", name_keys=("name", "prompt", "template"), extra_keys=("current_version", "previous_version", "workflow", "severity")) for i, row in enumerate(prompts, 1)], "rollback_triggers": section(hints, ("rollback_triggers", "triggers", "thresholds"), "PRT", "prompt_owner", "Define prompt rollback trigger", evidence_ids, ["quality regression, safety defect, latency spike, cost increase, or customer escalation threshold"]), "rollback_sequence": _sequence(prompts, evidence_ids), "validation_steps": section(hints, ("validation_steps", "validation"), "PRV", "evaluation_owner", "Validate prompt rollback", evidence_ids, ["rerun golden scenarios, compare previous prompt outputs, verify safety filters, and sample production traces"]), "owner_assignments": section(hints, ("owner_assignments", "owners"), "PRO", "prompt_owner", "Assign rollback owner", evidence_ids, ["prompt owner, workflow owner, evaluator, and incident lead"]), "communication": section(hints, ("communication", "comms"), "PRC", "support_owner", "Communicate prompt rollback", evidence_ids, ["notify affected workflow owners, support, customer success, and release channel"]), "monitoring_windows": section(hints, ("monitoring_windows", "monitoring"), "PRM", "prompt_owner", "Monitor prompt rollback", evidence_ids, ["monitor quality, safety, latency, and escalation metrics for 24 hours after rollback"]), "risk_flags": _flags(prompts, evidence_ids), "evidence_references": ctx["evidence_references"]}


def _sequence(prompts: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [item("PRS", i, {"name": compact(row.get("name")), "description": "Restore previous prompt version, invalidate prompt cache, and redeploy workflow configuration."}, "prompt_owner", evidence_ids, "Roll back prompt") for i, row in enumerate(prompts, 1)]


def _flags(prompts: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    flags = []
    for row in prompts:
        if not compact(row.get("previous_version")) or compact(row.get("previous_version")).lower() == "missing":
            flags.append(item("PRF", len(flags) + 1, {"name": compact(row.get("name")), "severity": "high", "description": "Missing previous prompt version blocks automated rollback until an approved baseline is selected."}, "prompt_owner", evidence_ids, "Flag prompt rollback risk"))
        elif _rank(row) == 0:
            flags.append(item("PRF", len(flags) + 1, {"name": compact(row.get("name")), "severity": "critical", "description": "Critical prompt regression must roll back before lower-risk prompts."}, "prompt_owner", evidence_ids, "Flag prompt rollback risk"))
    return flags or [item("PRF", 1, {"name": "rollback inputs ready", "severity": "low"}, "prompt_owner", evidence_ids, "Record prompt rollback readiness")]


def _rank(row: dict[str, Any]) -> int:
    return 0 if compact(row.get("severity")).lower() == "critical" else (1 if compact(row.get("severity")).lower() == "high" else 2)
