"""Generate deterministic inference latency degradation response plans."""

from __future__ import annotations

from typing import Any, Mapping

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.inference_latency_degradation_plan.v1"
KIND = "max.spec.inference_latency_degradation_plan"


def generate_inference_latency_degradation_plan(spec_like: Any) -> dict[str, Any]:
    """Return a deterministic plan for degraded LLM inference latency."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec, ctx)
    findings = _breach_findings(hints)
    status = "breached" if findings else "watch"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            status=status,
            model=hints["model"],
            provider=hints["provider"],
            affected_route_count=len(hints["affected_routes"]),
            breach_count=len(findings),
        ),
        "latency_profile": {
            "model": hints["model"],
            "provider": hints["provider"],
            "affected_routes": hints["affected_routes"],
            "observed_ms": hints["observed_ms"],
            "target_ms": hints["target_ms"],
        },
        "breach_findings": findings,
        "triage": _triage(hints, findings),
        "mitigation": _mitigation(hints, findings),
        "rollback": _rollback(hints, findings),
        "monitoring_checks": _monitoring_checks(hints, findings),
        "owner_handoff": _owner_handoff(hints, status),
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    metadata = _mapping(spec.get("metadata"))
    latency = _mapping(metadata.get("inference_latency") or spec.get("inference_latency"))
    metrics = _mapping(latency.get("metrics") or latency.get("observed_ms") or metadata.get("latency_metrics"))
    targets = _mapping(latency.get("targets") or latency.get("target_ms") or metadata.get("latency_targets"))
    solution = _mapping(spec.get("solution"))
    provider = compact(latency.get("provider") or solution.get("provider") or metadata.get("provider")) or "primary LLM provider"
    model = compact(latency.get("model") or solution.get("model") or metadata.get("model")) or "primary inference model"
    routes = (
        string_list(latency.get("affected_routes"))
        or string_list(latency.get("routes"))
        or string_list(metadata.get("affected_routes"))
        or ctx["mvp_scope"]
        or ["primary inference route"]
    )
    return {
        "provider": provider,
        "model": model,
        "affected_routes": _ordered(routes),
        "observed_ms": {key: _number(metrics.get(key)) for key in ("p50", "p95", "p99")},
        "target_ms": {
            "p50": _number(targets.get("p50")) or 1000,
            "p95": _number(targets.get("p95") or latency.get("target_p95_ms")) or 2500,
            "p99": _number(targets.get("p99") or latency.get("target_p99_ms")) or 5000,
        },
        "owners": _ordered(string_list(latency.get("owners")) or ["inference_owner", "sre_owner"]),
    }


def _breach_findings(hints: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for metric in ("p95", "p99"):
        observed = hints["observed_ms"].get(metric)
        target = hints["target_ms"][metric]
        if observed is not None and observed > target:
            findings.append(
                {
                    "id": f"LAT-{metric.upper()}",
                    "metric": metric,
                    "observed_ms": observed,
                    "target_ms": target,
                    "over_target_ms": observed - target,
                    "severity": "critical" if observed >= target * 1.5 else "high",
                    "affected_routes": hints["affected_routes"],
                }
            )
    return findings


def _triage(hints: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity = "high" if findings else "medium"
    return [
        _row("TRI1", "Confirm degradation scope", "sre_owner", severity, f"Compare p50/p95/p99 latency for {hints['model']} across affected routes."),
        _row("TRI2", "Provider and model health check", "inference_owner", severity, f"Check {hints['provider']} status, queue depth, timeout rate, and recent model configuration changes."),
        _row("TRI3", "Customer impact classification", "support_owner", severity, "Identify affected tenants, retry amplification, and any SLA-impacting workflows."),
    ]


def _mitigation(hints: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity = "critical" if any(item["severity"] == "critical" for item in findings) else "high"
    return [
        _row("MIT1", "Routing mitigation", "traffic_owner", severity, "Shift traffic away from saturated regions, providers, or routes and cap concurrency on degraded paths."),
        _row("MIT2", "Cache fallback", "platform_owner", "high", "Increase safe prompt/result cache use for repeatable requests while preserving freshness-sensitive paths."),
        _row("MIT3", "Model fallback", "inference_owner", "high", f"Route eligible requests from {hints['model']} to an approved lower-latency fallback model."),
        _row("MIT4", "Load shedding", "sre_owner", "medium", "Apply queued-request limits and graceful degradation for non-critical inference workloads."),
    ]


def _rollback(hints: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _row("RB1", "Restore prior routing", "traffic_owner", "high", "Rollback recent routing, prompt, provider, or model changes if latency does not recover after mitigation."),
        _row("RB2", "Disable risky rollout", "release_owner", "high" if findings else "medium", "Pause the latest inference rollout and restore the last known-good configuration."),
    ]


def _monitoring_checks(hints: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _row("MON1", "Percentile latency alerts", "sre_owner", "high", "Alert on p95 and p99 latency by model, provider, tenant tier, and route."),
        _row("MON2", "Fallback effectiveness", "inference_owner", "medium", "Track fallback volume, cache hit rate, timeout rate, and response quality regressions."),
        _row("MON3", "Recovery gate", "incident_commander", "medium", "Hold mitigations until p95 and p99 remain under target for two consecutive monitoring windows."),
    ]


def _owner_handoff(hints: dict[str, Any], status: str) -> list[dict[str, Any]]:
    return [
        {
            "id": f"OWN{index}",
            "owner": owner,
            "status": "action_required" if status == "breached" else "watch",
            "handoff": "Own mitigation and status updates for inference latency degradation.",
        }
        for index, owner in enumerate(hints["owners"], start=1)
    ]


def _row(item_id: str, name: str, owner: str, severity: str, action: str) -> dict[str, Any]:
    return {"id": item_id, "name": name, "owner": owner, "severity": severity, "action": action}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _ordered(values: list[str]) -> list[str]:
    return list(dict.fromkeys(compact(value) for value in values if compact(value)))
