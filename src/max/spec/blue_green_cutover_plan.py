"""Generate deterministic blue/green cutover plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary

SCHEMA_VERSION = "max.spec.blue_green_cutover_plan.v1"
KIND = "max.spec.blue_green_cutover_plan"


def generate_blue_green_cutover_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "blue_green_cutover")
    service = compact(hints.get("service")) or ctx["workflow_context"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, service=service, cutoff_window=compact(hints.get("cutoff_window")) or "scheduled release window"),
        "plan_title": f"{service} blue/green cutover",
        "scope": {"service": service, "blue_environment": compact(hints.get("blue_environment")) or "blue", "green_environment": compact(hints.get("green_environment")) or "green"},
        "cutover_phases": section(hints, ("traffic_phases", "phases"), "BGP", "release_owner", "Shift blue/green traffic phase", evidence_ids, ["0% green health check", "10% green canary", "50% green ramp", "100% green cutover"]),
        "validation_probes": section(hints, ("validation_probes", "probes"), "BGV", "qa_owner", "Validate green environment", evidence_ids, ["synthetic smoke test", "read/write probe", "customer journey probe"]),
        "rollback_criteria": section(hints, ("rollback_triggers", "rollback_criteria", "rollback"), "BGR", "on_call_owner", "Rollback to blue", evidence_ids, ["probe failure", "elevated errors", "latency regression"]),
        "communications": section(hints, ("communications", "notices"), "BGC", "release_manager", "Communicate cutover status", evidence_ids, ["announce start, ramp checkpoints, completion, and rollback decision path"]),
        "signoff": section(hints, ("owner_roles", "signoff"), "BGS", "program_owner", "Sign off blue/green cutover", evidence_ids, ["release, engineering, QA, on-call owner signoff"]),
        "evidence_references": ctx["evidence_references"],
    }
