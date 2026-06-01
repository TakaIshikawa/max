"""Generate deterministic model provider failover drill plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact


SCHEMA_VERSION = "max.spec.model_provider_failover_drill_plan.v1"
KIND = "max.spec.model_provider_failover_drill_plan"


def generate_model_provider_failover_drill_plan(
    providers: Any,
    scenarios: Any,
    *,
    rollback_window_minutes: int = 30,
) -> dict[str, Any]:
    provider_rows = _providers(providers)
    scenario_rows = _scenarios(scenarios)
    blockers = _fallback_blockers(provider_rows)
    validation_checks = _validation_checks(scenario_rows)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "provider_count": len(provider_rows),
            "scenario_count": len(scenario_rows),
            "blocker_count": len(blockers),
            "rollback_window_minutes": max(0, int(rollback_window_minutes)),
            "status": "blocked" if blockers else "ready",
        },
        "providers": provider_rows,
        "scenarios": scenario_rows,
        "blockers": blockers,
        "prechecks": [
            _row("MPFDP", 1, "confirm fallback routing", "ml_platform_owner", "Verify every in-scope provider has fallback provider, quota, credentials, and routing rules configured."),
            _row("MPFDP", 2, "freeze drill baseline", "sre_owner", "Capture baseline latency, error rate, quality score, cost, and active traffic share before the drill."),
            _row("MPFDP", 3, "notify drill owners", "incident_commander", "Confirm on-call, evaluation, finance, and customer support owners are aware of the scheduled failover drill."),
        ],
        "execution": [
            _row("MPFDE", 1, "start canary shift", "release_manager", "Shift 5 percent of eligible model traffic from each primary provider to its configured fallback."),
            _row("MPFDE", 2, "expand traffic shift", "release_manager", "Increase fallback traffic through 25, 50, and 100 percent gates when validation probes remain green."),
            _row("MPFDE", 3, "hold steady state", "sre_owner", "Maintain fallback routing long enough to collect request, latency, quality, and cost evidence for each scenario."),
        ],
        "validation": validation_checks,
        "rollback": [
            _row(
                "MPFDR",
                1,
                "rollback window",
                "incident_commander",
                f"Restore primary-provider routing within {max(0, int(rollback_window_minutes))} minutes when rollback criteria are met.",
                criteria=[
                    "fallback error rate exceeds threshold",
                    "quality probe regression exceeds tolerance",
                    "fallback quota or spend guardrail is breached",
                    "customer-impacting latency persists for two consecutive checks",
                ],
            )
        ],
        "evidence": [
            _row("MPFDV", 1, "routing evidence", "sre_owner", "Archive traffic-shift audit logs, provider status pages, and routing configuration diffs."),
            _row("MPFDV", 2, "validation evidence", "evaluation_owner", "Attach validation probe results, sampled prompt outputs, latency charts, and cost deltas."),
            _row("MPFDV", 3, "decision evidence", "incident_commander", "Record rollback decisions, signoffs, timeline notes, and follow-up owners."),
        ],
    }


def _providers(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    rows = []
    for index, item in enumerate(raw, start=1):
        record = item if isinstance(item, dict) else {"name": item}
        name = compact(record.get("name") or record.get("provider") or record.get("id")) or f"provider-{index}"
        fallback = compact(
            record.get("fallback_provider")
            or record.get("fallback")
            or record.get("backup_provider")
            or record.get("secondary_provider")
        )
        rows.append(
            {
                "id": f"MPFDPV{index}",
                "name": name,
                "owner": compact(record.get("owner")) or "ml_platform_owner",
                "fallback_provider": fallback,
                "traffic_share": compact(record.get("traffic_share") or record.get("traffic")) or "in scope",
            }
        )
    return sorted(rows, key=lambda row: row["name"].casefold())


def _scenarios(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    rows = []
    for index, item in enumerate(raw, start=1):
        record = item if isinstance(item, dict) else {"name": item}
        name = compact(record.get("name") or record.get("scenario") or record.get("id")) or f"scenario-{index}"
        rows.append(
            {
                "id": f"MPFDS{index}",
                "name": name,
                "priority": _priority(record.get("priority")),
                "trigger": compact(record.get("trigger")) or "provider degradation",
                "validation_probes": _list(record.get("validation_probes") or record.get("validation") or record.get("checks")),
            }
        )
    rows.sort(key=lambda row: (row["priority"], row["name"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"MPFDS{index}"
    return rows


def _fallback_blockers(providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _row(
            "MPFDB",
            index,
            f"{provider['name']} fallback missing",
            provider["owner"],
            f"Configure a fallback provider before running the drill for {provider['name']}.",
            provider=provider["name"],
            severity="critical",
        )
        for index, provider in enumerate((item for item in providers if not item["fallback_provider"]), start=1)
    ]


def _validation_checks(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = []
    for scenario in scenarios:
        probes = scenario["validation_probes"] or [
            "availability probe",
            "latency SLO probe",
            "quality regression probe",
            "cost and quota probe",
        ]
        for probe in probes:
            checks.append(
                _row(
                    "MPFDV",
                    len(checks) + 1,
                    f"{scenario['name']}: {probe}",
                    "evaluation_owner",
                    f"Run {probe} during the {scenario['name']} failover scenario.",
                    scenario=scenario["name"],
                )
            )
    return checks or [
        _row("MPFDV", 1, "default failover probes", "evaluation_owner", "Run availability, latency, quality, quota, and cost probes during the provider failover drill.")
    ]


def _row(prefix: str, index: int, name: str, owner: str, description: str, **extra: Any) -> dict[str, Any]:
    row = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description}
    row.update({key: value for key, value in extra.items() if value not in (None, "", [])})
    return row


def _priority(value: Any) -> int:
    if value is None or value == "":
        return 999
    try:
        return int(value)
    except (TypeError, ValueError):
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(compact(value).lower(), 999)


def _list(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else ([value] if value not in (None, "") else [])
    return [compact(item.get("name") if isinstance(item, dict) else item) for item in raw if compact(item.get("name") if isinstance(item, dict) else item)]
