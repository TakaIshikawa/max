"""Generate deterministic prompt change impact review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.prompt_change_impact_review_plan.v1"
KIND = "max.spec.prompt_change_impact_review_plan"
HIGH_IMPACT_STAGES = {"safety", "scoring", "spec-generation", "spec_generation"}


def generate_prompt_change_impact_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "prompt_change_impact_review")
    changes = unique_records(named(hints.get("prompt_changes") or hints.get("prompts") or hints.get("diffs"), ("prompt", "stage", "after")), [{"name": "prompt version change", "stage": "generation"}])
    prompt_changes = [_change_row(record, index, evidence_ids) for index, record in enumerate(changes, start=1)]
    high_impact = [row for row in prompt_changes if row["impact_level"] == "high"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, prompt_change_count=len(prompt_changes), high_impact_change_count=len(high_impact)),
        "prompt_changes": prompt_changes,
        "affected_workflows": section(hints, ("affected_workflows", "workflows", "pipeline_stages", "stages"), "PCW", "product_owner", "Review affected workflow", evidence_ids, ["generation, evaluation, scoring, safety, and spec-generation workflows"]),
        "evaluation_checks": section(hints, ("evaluation_checks", "evals", "checks"), "PCE", "evaluation_owner", "Run prompt change evaluation check", evidence_ids, ["baseline comparison, golden set replay, safety eval, and regression review"]),
        "safety_privacy_review": section(hints, ("safety_privacy_review", "safety", "privacy"), "PCS", "safety_owner", "Review prompt safety and privacy impact", evidence_ids, ["prompt injection, sensitive data, policy bypass, and jailbreak resistance review"]),
        "rollout_gates": section(hints, ("rollout_gates", "gates", "rollout"), "PCR", "release_owner", "Gate prompt rollout", evidence_ids, ["canary, approval, rollback, and customer communication gates"]),
        "monitoring_signals": section(hints, ("monitoring_signals", "monitoring", "signals"), "PCM", "model_owner", "Monitor prompt change signal", evidence_ids, ["quality, refusal, safety, cost, latency, and support signals"]),
        "high_impact_changes": high_impact,
        "evidence_references": ctx["evidence_references"],
    }


def _change_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    stage = compact(record.get("stage") or record.get("pipeline_stage"))
    impact = "high" if stage.lower() in HIGH_IMPACT_STAGES or compact(record.get("severity")).lower() in {"high", "critical"} else "medium"
    return row("PCC", index, compact(record.get("name") or record.get("prompt") or record.get("stage")) or "prompt version change", compact(record.get("owner")) or "prompt_owner", "Review prompt diff before rollout.", evidence_ids, before=compact(record.get("before") or record.get("before_version")), after=compact(record.get("after") or record.get("after_version")), stage=stage, impact_level=impact)
