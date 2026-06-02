"""Generate deterministic prompt evaluation regression triage plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, summary
from max.spec._review_plan_common import base, ordered, row, values

SCHEMA_VERSION = "max.spec.prompt_evaluation_regression_triage_plan.v1"
KIND = "max.spec.prompt_evaluation_regression_triage_plan"


def generate_prompt_evaluation_regression_triage_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "prompt_evaluation_regression_triage")
    _require(hints, ("prompt_name", "prompt_version", "baseline_version", "failed_metrics", "affected_profiles", "owner"))
    owner = compact(hints["owner"])
    severity = compact(hints.get("severity")).lower() or "medium"
    metrics = values(hints.get("failed_metrics"), [])
    profiles = values(hints.get("affected_profiles"), [])

    release_gate = [row("PERG", 1, "Immediate release gate", owner, "Block prompt release while high-severity evaluation regression is triaged.", evidence_ids, severity=severity)] if severity in {"high", "critical"} else []
    release_gate.append(row("PERG", len(release_gate) + 1, "Release gate approval", owner, "Require metric recovery and profile owner approval before promotion.", evidence_ids, required=True))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, prompt_name=compact(hints["prompt_name"]), prompt_version=compact(hints["prompt_version"]), baseline_version=compact(hints["baseline_version"]), severity=severity),
        "metric_triage": [row("PEMT", index, metric, owner, f"Compare failed metric {metric} against baseline and release threshold.", evidence_ids, metric=metric) for index, metric in enumerate(metrics, 1)],
        "sample_review": [row("PESR", index, profile, owner, f"Review failed prompt samples for affected profile {profile}.", evidence_ids, profile=profile) for index, profile in enumerate(profiles, 1)],
        "rollback_decision": [row("PERD", 1, "Rollback candidate decision", owner, "Decide whether to roll back to baseline or hold current prompt behind a gate.", evidence_ids, rollback_candidate=compact(hints.get("rollback_candidate")) or "to be decided")],
        "remediation": [row("PERM", 1, "Prompt remediation", owner, "Patch prompt, rerun failed metrics, and record evaluation deltas.", evidence_ids)],
        "release_gate": release_gate,
        "evidence_references": ctx["evidence_references"],
    }


def _require(hints: dict[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if not values(hints.get(key), [])]
    if missing:
        raise ValueError(f"Missing prompt evaluation regression triage fields: {', '.join(ordered(missing))}")
