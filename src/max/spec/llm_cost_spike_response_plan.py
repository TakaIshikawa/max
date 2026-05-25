"""Generate deterministic LLM cost spike response plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.llm_cost_spike_response_plan.v1"
KIND = "max.spec.llm_cost_spike_response_plan"


def generate_llm_cost_spike_response_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "llm_cost_spike_response")
    thresholds = unique_records(
        named(hints.get("trigger_thresholds") or hints.get("thresholds") or hints.get("triggers"), ("threshold", "metric")),
        [{"name": "unexpected LLM spend increase", "metric": "daily spend", "threshold": ">= 25% over baseline"}],
    )
    spike_type = str(hints.get("spike_type") or hints.get("type") or "").lower()
    containment_fallback = (
        ["lower max tokens, cache repeated prompts, rate-limit high-token workflows, and inspect prompt expansion"]
        if "token" in spike_type
        else ["switch to approved lower-cost model, enforce budget cap, throttle noncritical traffic, and verify price book"]
        if "price" in spike_type
        else ["enforce spend cap, throttle noncritical traffic, inspect token usage, and verify model pricing"]
    )
    risks = list(hints.get("risks") or [])
    if not any(key in hints for key in ("baseline", "baselines", "cost_baseline")):
        risks.append({"name": "missing cost baseline", "severity": "high", "description": "Cost spike cannot be sized without an approved baseline."})
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, threshold_count=len(thresholds)),
        "trigger_thresholds": [
            item(
                "LCT",
                index,
                record,
                "finance_owner",
                evidence_ids,
                "Define LLM cost spike trigger",
                name_keys=("name", "threshold", "metric"),
                extra_keys=("metric", "threshold", "baseline", "window"),
            )
            for index, record in enumerate(thresholds, start=1)
        ],
        "affected_surfaces": section(
            hints,
            ("affected_surfaces", "affected_stages", "models", "profiles"),
            "LCS",
            "ml_platform_owner",
            "Identify affected LLM cost surface",
            evidence_ids,
            ["affected stages, models, tenants, workflows, and evaluation profiles"],
            name_keys=("name", "stage", "model", "profile"),
            extra_keys=("stage", "model", "profile", "spend"),
        ),
        "containment_actions": section(
            hints,
            ("containment_actions", "containment", "immediate_actions"),
            "LCC",
            "ml_platform_owner",
            "Contain LLM cost spike",
            evidence_ids,
            containment_fallback,
        ),
        "investigation_evidence": section(
            hints,
            ("investigation_evidence", "evidence", "diagnostics"),
            "LCI",
            "analytics_owner",
            "Investigate LLM cost spike evidence",
            evidence_ids,
            ["token usage, request volume, model mix, unit prices, cache hit rate, and deployment changes"],
        ),
        "owner_assignments": section(
            hints,
            ("owner_assignments", "owners", "owner_checklist"),
            "LCO",
            "program_owner",
            "Assign LLM cost spike owner",
            evidence_ids,
            ["finance, ML platform, product, analytics, and incident commander owners assigned"],
        ),
        "recovery_options": section(
            hints,
            ("recovery_options", "rollback", "throttle_options"),
            "LCR",
            "release_manager",
            "Recover from LLM cost spike",
            evidence_ids,
            ["rollback prompt or model change, keep throttles until spend normalizes, and restore budgets gradually"],
        ),
        "risks": section({"risks": risks}, ("risks",), "LCK", "risk_owner", "Review LLM cost spike risk", evidence_ids, []),
        "acceptance_criteria": section(
            hints,
            ("acceptance_criteria", "closure_criteria"),
            "LCA",
            "program_owner",
            "Accept LLM cost spike response",
            evidence_ids,
            ["spend returns within threshold, root cause is documented, containment is reviewed, and recovery is approved"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
