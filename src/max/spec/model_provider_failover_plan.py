"""Generate deterministic model provider failover plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.model_provider_failover_plan.v1"
KIND = "max.spec.model_provider_failover_plan"


def generate_model_provider_failover_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_provider_failover")
    providers = unique_records(
        named(hints.get("providers") or hints.get("provider_inventory"), ("provider", "model")),
        [{"name": "primary model provider", "owner": "ml_platform_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, provider_count=len(providers)),
        "provider_inventory": [
            item("MPF", index, record, "ml_platform_owner", evidence_ids, "Inventory model provider", name_keys=("name", "provider", "model"), extra_keys=("provider", "model", "role", "impact"))
            for index, record in enumerate(providers, start=1)
        ],
        "failover_triggers": section(hints, ("triggers", "failover_triggers"), "MPT", "incident_commander", "Define failover trigger", evidence_ids, ["outage, cost, latency, policy, or safety trigger"]),
        "compatibility_checks": section(hints, ("compatibility_checks", "compatibility"), "MPC", "ml_platform_owner", "Run provider compatibility check", evidence_ids, ["API, context window, tool, and policy compatibility"]),
        "prompt_regression_validation": section(hints, ("prompt_regression_validation", "validation", "regression_tests"), "MPV", "quality_owner", "Validate prompts and regressions", evidence_ids, ["golden prompt and regression suite"]),
        "budget_guardrails": section(hints, ("budget_guardrails", "budget_controls"), "MPB", "finance_owner", "Enforce budget guardrail", evidence_ids, ["cost cap and spend anomaly alert"]),
        "rollout_steps": section(hints, ("rollout", "rollout_steps"), "MPR", "release_manager", "Roll out provider failover", evidence_ids, ["canary, staged traffic shift, and approval gate"]),
        "monitoring": section(hints, ("monitoring", "monitors"), "MPM", "on_call_owner", "Monitor provider failover", evidence_ids, ["latency, quality, error, and cost dashboard"]),
        "rollback": section(hints, ("rollback", "rollback_steps"), "MPX", "ml_platform_owner", "Rollback provider failover", evidence_ids, ["restore primary provider routing"]),
        "evidence_references": ctx["evidence_references"],
    }
