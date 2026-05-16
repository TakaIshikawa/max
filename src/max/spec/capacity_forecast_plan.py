"""Generate deterministic capacity forecast plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, string_list, summary


SCHEMA_VERSION = "max.spec.capacity_forecast_plan.v1"
CAPACITY_FORECAST_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.capacity_forecast_plan"


def generate_capacity_forecast_plan(spec_like: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic launch capacity guidance from a TactSpec-like payload."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _capacity_hints(spec)
    evidence_ids = [item["id"] for item in ctx["evidence_references"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            forecast_posture=_forecast_posture(hints),
            expected_users=hints["expected_users"],
            requests_per_day=hints["requests_per_day"],
            support_volume=hints["support_volume"],
            data_volume=hints["data_volume"],
        ),
        "demand_assumptions": _demand_assumptions(ctx, hints, evidence_ids),
        "capacity_drivers": _capacity_drivers(ctx, hints, evidence_ids),
        "resource_forecasts": _resource_forecasts(ctx, hints, evidence_ids),
        "scaling_triggers": _scaling_triggers(ctx, hints, evidence_ids),
        "measurement_plan": _measurement_plan(ctx, hints, evidence_ids),
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _capacity_hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    capacity = metadata.get("capacity") if isinstance(metadata.get("capacity"), dict) else {}
    launch = metadata.get("launch") if isinstance(metadata.get("launch"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}

    def hinted_number(*keys: str) -> float | None:
        for payload in (capacity, metadata, launch, execution):
            for key in keys:
                found = number(payload.get(key))
                if found is not None:
                    return found
        return None

    return {
        "expected_users": hinted_number("expected_users", "target_users", "users", "launch_users"),
        "requests_per_day": hinted_number("requests_per_day", "daily_requests", "request_volume"),
        "support_volume": hinted_number("support_volume", "support_tickets_per_day", "tickets_per_day"),
        "data_volume": compact(
            capacity.get("data_volume")
            or metadata.get("data_volume")
            or launch.get("data_volume")
            or execution.get("data_volume")
        )
        or None,
    }


def _demand_assumptions(
    ctx: dict[str, Any], hints: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    users = hints["expected_users"]
    requests = hints["requests_per_day"]
    support = hints["support_volume"]
    data_volume = hints["data_volume"]
    return [
        _item(
            "DA1",
            "Launch audience",
            "demand",
            f"Plan initial launch for {int(users) if users is not None else 'Unknown'} expected users in {ctx['workflow_context']}.",
            "metadata.capacity.expected_users" if users is not None else "project.target_users",
            "product_owner",
            evidence_ids,
        ),
        _item(
            "DA2",
            "Request throughput",
            "demand",
            f"Assume {int(requests) if requests is not None else 'Unknown'} customer or system requests per day at launch.",
            "metadata.capacity.requests_per_day" if requests is not None else "execution.validation_plan",
            "technical_owner",
            evidence_ids,
        ),
        _item(
            "DA3",
            "Support load",
            "demand",
            f"Reserve support capacity for {int(support) if support is not None else 'Unknown'} launch support tickets per day.",
            "metadata.capacity.support_volume" if support is not None else "execution.risks",
            "support_owner",
            evidence_ids,
        ),
        _item(
            "DA4",
            "Data growth",
            "demand",
            f"Use {data_volume or 'Unknown'} as the initial data volume assumption for storage, backups, and analytics.",
            "metadata.capacity.data_volume" if data_volume else "solution.suggested_stack",
            "data_owner",
            evidence_ids,
        ),
    ]


def _capacity_drivers(
    ctx: dict[str, Any], hints: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    mvp_scope = ctx["mvp_scope"] or ["first usable workflow"]
    stack = ctx["stack_label"] or "Unknown stack"
    return [
        _item(
            "CD1",
            "MVP workflow breadth",
            "driver",
            f"Capacity must cover {', '.join(mvp_scope)} without queueing launch-critical work.",
            "execution.mvp_scope",
            "product_owner",
            evidence_ids,
        ),
        _item(
            "CD2",
            "Solution stack limits",
            "driver",
            f"Validate runtime, datastore, queue, cache, and integration limits for {stack}.",
            "solution.suggested_stack",
            "technical_owner",
            evidence_ids,
        ),
        _item(
            "CD3",
            "Data and retention pressure",
            "driver",
            f"Forecast storage, indexing, backup, and export pressure from {hints['data_volume'] or 'Unknown'} launch data volume.",
            "metadata.capacity.data_volume",
            "data_owner",
            evidence_ids,
        ),
    ]


def _resource_forecasts(
    ctx: dict[str, Any], hints: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    requests = hints["requests_per_day"]
    support = hints["support_volume"]
    data_volume = hints["data_volume"]
    return [
        _forecast(
            "RF1",
            "Application runtime",
            "technical_owner",
            _runtime_capacity(requests),
            "p95 latency, error rate, queue depth, and saturation during launch windows",
            evidence_ids,
        ),
        _forecast(
            "RF2",
            "Datastore and storage",
            "data_owner",
            f"Provision storage and backup headroom for {data_volume or 'Unknown launch data volume'} plus 30 days of launch growth.",
            "storage used, index size, backup duration, restore test duration",
            evidence_ids,
        ),
        _forecast(
            "RF3",
            "Support staffing",
            "support_owner",
            _support_capacity(support),
            "open tickets, first response time, blocker age, and escalation count",
            evidence_ids,
        ),
        _forecast(
            "RF4",
            "Integration and vendor quota",
            "vendor_owner",
            f"Confirm vendor quotas cover {ctx['workflow_context']} peak load with 25% reserve.",
            "rate-limit responses, retry count, vendor quota utilization",
            evidence_ids,
        ),
    ]


def _scaling_triggers(
    ctx: dict[str, Any], hints: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    requests = hints["requests_per_day"]
    users = hints["expected_users"]
    return [
        _trigger(
            "ST1",
            "Traffic reserve breached",
            "technical_owner",
            f"Requests exceed {_threshold(requests, 0.8, 'Unknown')} per day or p95 latency exceeds 2 seconds for two review windows.",
            "add runtime capacity, increase queue workers, or defer non-critical jobs",
            evidence_ids,
        ),
        _trigger(
            "ST2",
            "Launch audience expands",
            "product_owner",
            f"Active launch users exceed {_threshold(users, 0.9, 'Unknown')} or next cohort would increase users by more than 25%.",
            "review cohort gating, support readiness, and datastore headroom before expansion",
            evidence_ids,
        ),
        _trigger(
            "ST3",
            "Support backlog grows",
            "support_owner",
            "First response SLA misses two consecutive launch review windows or blockers age beyond one business day.",
            "add staffed support coverage and pause expansion until backlog returns to target",
            evidence_ids,
        ),
    ]


def _measurement_plan(
    ctx: dict[str, Any], hints: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        _metric(
            "MP1",
            "request_volume",
            "requests per day and peak requests per minute",
            "hourly during staffed launch windows, daily otherwise",
            "technical_owner",
            evidence_ids,
        ),
        _metric(
            "MP2",
            "active_launch_users",
            f"active users against {hints['expected_users'] or 'Unknown'} expected users",
            "daily through first two launch cohorts",
            "product_owner",
            evidence_ids,
        ),
        _metric(
            "MP3",
            "support_load",
            f"new tickets and blockers against {hints['support_volume'] or 'Unknown'} expected daily support volume",
            "twice daily during staffed launch",
            "support_owner",
            evidence_ids,
        ),
        _metric(
            "MP4",
            "data_growth",
            f"stored records, export size, and backup duration for {ctx['workflow_context']}",
            "daily until growth trend is stable",
            "data_owner",
            evidence_ids,
        ),
    ]


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": "product_owner",
            "suggested_owner": ctx["buyer"],
            "responsibility": "Own cohort sizing, launch gates, and demand assumption approval.",
        },
        {
            "role": "technical_owner",
            "suggested_owner": "technical_owner",
            "responsibility": "Own runtime sizing, observability, scaling actions, and quota checks.",
        },
        {
            "role": "data_owner",
            "suggested_owner": "data_owner",
            "responsibility": "Own storage, backup, restore, retention, and data growth forecasts.",
        },
        {
            "role": "support_owner",
            "suggested_owner": "support_owner",
            "responsibility": "Own launch support coverage, ticket triage, and escalation capacity.",
        },
    ]


def _item(
    item_id: str,
    name: str,
    item_type: str,
    description: str,
    source_field: str,
    owner: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "type": item_type,
        "owner": owner,
        "description": description,
        "source_field": source_field,
        "evidence_reference_ids": evidence_ids,
    }


def _forecast(
    item_id: str,
    resource: str,
    owner: str,
    forecast: str,
    measurement: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "resource": resource,
        "owner": owner,
        "forecast": forecast,
        "measurement": measurement,
        "evidence_reference_ids": evidence_ids,
    }


def _trigger(
    item_id: str,
    name: str,
    owner: str,
    condition: str,
    action: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "condition": condition,
        "action": action,
        "evidence_reference_ids": evidence_ids,
    }


def _metric(
    item_id: str,
    name: str,
    measurement: str,
    cadence: str,
    owner: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "measurement": measurement,
        "cadence": cadence,
        "owner": owner,
        "evidence_reference_ids": evidence_ids,
    }


def _runtime_capacity(requests_per_day: float | None) -> str:
    if requests_per_day is None:
        return "Baseline one production slice plus one standby slice until request volume is measured."
    peak_per_minute = max(1, round(requests_per_day / 1440 * 4))
    return f"Provision for at least {int(requests_per_day)} requests per day and {peak_per_minute} peak requests per minute with 25% reserve."


def _support_capacity(support_volume: float | None) -> str:
    if support_volume is None:
        return "Assign named launch support coverage and measure first response before expanding cohorts."
    return f"Staff coverage for {int(support_volume)} new support tickets per day with same-business-day triage."


def _threshold(value: float | None, ratio: float, fallback: str) -> str:
    if value is None:
        return fallback
    return str(max(1, int(value * ratio)))


def _forecast_posture(hints: dict[str, Any]) -> str:
    if hints["expected_users"] is None and hints["requests_per_day"] is None:
        return "needs_capacity_discovery"
    if (hints["expected_users"] or 0) >= 1000 or (hints["requests_per_day"] or 0) >= 10000:
        return "scale_test_before_launch"
    return "staffed_launch_monitoring"
