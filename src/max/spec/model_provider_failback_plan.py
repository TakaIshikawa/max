"""Generate deterministic model provider failback plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._review_plan_common import base, source_summary

SCHEMA_VERSION = "max.spec.model_provider_failback_plan.v1"
KIND = "max.spec.model_provider_failback_plan"


def generate_model_provider_failback_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_provider_failback")
    ramp = _ramp(hints.get("traffic_ramp") or hints.get("ramp_percentages") or [10, 25, 50, 100])
    health = hints.get("primary_provider_health") or hints.get("health_status") or "unknown"
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Model Provider Failback Plan", "summary": source_summary(ctx, ramp_steps=len(ramp), primary_provider_health=health), "incident_context": section(hints, ("incident_context", "incident"), "MPFIC", "incident_owner", "Document failback incident context", evidence_ids, ["backup provider is serving traffic after primary provider incident"]), "primary_provider_health_checks": section(hints, ("primary_provider_health_checks", "health_checks"), "MPFH", "ml_platform_owner", "Validate primary provider health", evidence_ids, ["availability, latency, error rate, quality, quota, and cost checks are green"], extra_keys=("status",)), "traffic_ramp": [{"id": f"MPFR{i}", "percentage": p, "description": f"Route {p}% of eligible traffic back to the primary provider.", "evidence_reference_ids": evidence_ids} for i, p in enumerate(ramp, 1)], "budget_guardrails": section(hints, ("budget_guardrails", "budget"), "MPFB", "finance_owner", "Apply failback budget guardrail", evidence_ids, ["compare primary and backup unit costs during ramp"]), "quality_regression_checks": section(hints, ("quality_regression_checks", "quality_checks"), "MPFQ", "evaluation_owner", "Run failback quality regression", evidence_ids, ["golden set and production shadow scores remain within tolerance"]), "rollback_triggers": section(hints, ("rollback_triggers", "triggers"), "MPFT", "incident_owner", "Define failback rollback trigger", evidence_ids, ["error, latency, quality, quota, or spend regression breaches threshold"]), "signoff": section(hints, ("signoff", "approvers"), "MPFA", "incident_owner", "Approve provider failback", evidence_ids, ["incident commander, ML platform, evaluation, and finance signoff"]), "evidence_references": ctx["evidence_references"]}


def _ramp(value: Any) -> list[int]:
    raw = value if isinstance(value, list) else [value]
    vals = []
    for item in raw:
        text = str(item).replace("%", "").strip()
        try:
            vals.append(max(0, min(100, int(float(text)))))
        except ValueError:
            pass
    return sorted(dict.fromkeys(vals)) or [10, 25, 50, 100]
