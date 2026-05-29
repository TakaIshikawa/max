"""Generate deterministic observability instrumentation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary

SCHEMA_VERSION = "max.spec.observability_instrumentation_plan.v1"
KIND = "max.spec.observability_instrumentation_plan"


def generate_observability_instrumentation_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "observability_instrumentation")
    service = compact(hints.get("service")) or ctx["workflow_context"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, service=service),
        "metrics": section(hints, ("metrics", "metric_signals"), "OIM", "observability_owner", "Instrument metric", evidence_ids, ["request rate", "error rate", "duration p95", "saturation"]),
        "logs": section(hints, ("logs", "logging"), "OIL", "engineering_owner", "Instrument structured log", evidence_ids, ["request correlation log", "business outcome log", "error context log"]),
        "traces": section(hints, ("traces", "tracing"), "OIT", "engineering_owner", "Instrument trace span", evidence_ids, ["ingress span", "dependency span", "persistence span"]),
        "alerts": section(hints, ("alerts", "alerting"), "OIA", "on_call_owner", "Configure alert", evidence_ids, ["SLO burn alert", "error spike alert", "dependency failure alert"]),
        "dashboards": section(hints, ("dashboards",), "OID", "observability_owner", "Create dashboard", evidence_ids, ["service overview with metrics, logs, traces, alerts, and ownership"]),
        "ownership": section(hints, ("ownership", "owners"), "OIO", "program_owner", "Assign telemetry owner", evidence_ids, ["service owner, on-call owner, dashboard owner"]),
        "rollout": section(hints, ("rollout",), "OIR", "release_owner", "Roll out instrumentation", evidence_ids, ["dev verification", "staging validation", "production canary"]),
        "verification": section(hints, ("verification", "checks"), "OIV", "qa_owner", "Verify instrumentation", evidence_ids, ["synthetic request emits metric, log, trace, alert, and dashboard signal"]),
        "maintenance": section(hints, ("maintenance",), "OIX", "observability_owner", "Maintain instrumentation", evidence_ids, ["quarterly dashboard and alert threshold review"]),
        "evidence_references": ctx["evidence_references"],
    }
