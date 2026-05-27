"""Generate deterministic SLO error budget recovery plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.slo_error_budget_recovery_plan.v1"
KIND = "max.spec.slo_error_budget_recovery_plan"


def generate_slo_error_budget_recovery_plan(inputs: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(inputs, "slo_error_budget_recovery")
    services = unique_records(named(hints.get("services") or hints.get("service_inventory"), ("service", "name")), [{"service": "primary service", "error_budget_remaining": 100, "burn_rate": 0, "slo_target": "99.9"}])
    inventory = sorted((_service_row(record, index, evidence_ids) for index, record in enumerate(services, start=1)), key=lambda item: ({"exhausted": 0, "fast_burn": 1, "watch": 2, "healthy": 3}[item["budget_status"]], item["service"].casefold()))
    breached = [item for item in inventory if item["budget_status"] != "healthy"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, service_count=len(inventory), breached_service_count=len(breached)),
        "service_inventory": inventory,
        "burn_rate_findings": breached,
        "freeze_recommendations": section(hints, ("freeze_recommendations", "freeze"), "SEF", "release_owner", "Apply reliability release freeze", evidence_ids, ["freeze risky launches until burn rate is below threshold"]),
        "reliability_backlog": section(hints, ("reliability_backlog", "backlog"), "SEB", "sre_owner", "Prioritize reliability backlog", evidence_ids, ["top error sources, rollback candidates, capacity fixes, and alert tuning"]),
        "customer_impact": section(hints, ("customer_impact", "impact"), "SEC", "support_owner", "Summarize customer impact", evidence_ids, ["affected customers, features, support tickets, and communication needs"]),
        "owners": section(hints, ("owners", "owner_assignments"), "SEO", "sre_owner", "Assign recovery owner", evidence_ids, ["incident commander, service owner, release owner, and customer communications"]),
        "checkpoints": section(hints, ("checkpoints", "reviews"), "SEK", "sre_owner", "Run recovery checkpoint", evidence_ids, ["hourly for exhausted budgets, daily for watch status"]),
        "exit_criteria": section(hints, ("exit_criteria", "criteria"), "SEE", "sre_owner", "Confirm recovery exit criteria", evidence_ids, ["budget positive, burn rate normal, alerts stable, and customer impact closed"]),
        "evidence_references": ctx["evidence_references"],
    }


def _service_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    remaining = _number(_first_present(record, "error_budget_remaining", "budget_remaining"), 100.0)
    burn = _number(record.get("burn_rate"), 0.0)
    target = compact(record.get("slo_target") or record.get("target")) or "target missing"
    if remaining <= 0:
        status, action = "exhausted", "freeze launches and run incident recovery"
    elif burn >= 2:
        status, action = "fast_burn", "freeze risky changes and reduce burn rate"
    elif burn >= 1 or target == "target missing":
        status, action = "watch", "monitor closely and close SLO target evidence gaps"
    else:
        status, action = "healthy", "continue monitoring and preserve error-budget guardrails"
    service = compact(record.get("service") or record.get("name")) or "primary service"
    return row("SES", index, service, compact(record.get("owner")) or "sre_owner", "Review SLO error budget recovery status.", evidence_ids, service=service, slo_target=target, error_budget_remaining=remaining, burn_rate=burn, budget_status=status, recommended_action=action)


def _number(value: Any, fallback: float) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return fallback


def _first_present(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None
