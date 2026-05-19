"""Generate deterministic integration cutover plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.integration_cutover_plan.v1"
KIND = "max.spec.integration_cutover_plan"


def generate_integration_cutover_plan(spec_like: Any) -> dict[str, Any]:
    """Return deterministic cutover planning data with conservative defaults."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec, "integration_cutover")
    systems = _values(hints.get("systems"), ["Primary application", "Integration endpoint"])
    external_dependencies = _values(hints.get("external_dependencies"), [])
    metrics = _values(hints.get("validation_metrics"), ["successful health check", "zero critical integration errors"])
    customer_impacting = _truthy(hints.get("customer_impacting"))
    strict = customer_impacting or bool(external_dependencies) or ctx["strictness"] == "strict"
    rollback_owner = compact(hints.get("rollback_owner")) or "engineering_owner"
    cutover_window = compact(hints.get("cutover_window")) or "scheduled maintenance window"
    freeze_period = compact(hints.get("freeze_period")) or ("24 hours before cutover" if strict else "during cutover window")
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            system_count=len(systems),
            external_dependency_count=len(external_dependencies),
            customer_impacting=customer_impacting,
            cutover_window=cutover_window,
        ),
        "cutover_strategy": [
            _item("CS1", "window_control", "release_manager", f"Execute cutover during {cutover_window}.", timing=cutover_window, references=["metadata.integration_cutover.cutover_window"], evidence_ids=evidence_ids),
            _item("CS2", "change_freeze", "release_manager", f"Freeze deploys and configuration changes {freeze_period}.", timing=freeze_period, references=["metadata.integration_cutover.freeze_period"], evidence_ids=evidence_ids),
            _item("CS3", "impact_control", "product_owner", "Treat the cutover as customer-impacting and keep support staffed." if strict else "Confirm no customer-visible workflow is expected to degrade.", severity="high" if strict else "medium", evidence_ids=evidence_ids),
        ],
        "dependency_readiness": [
            _item(f"DR{index}", system, "technical_owner", f"Confirm {system} is ready for the integration cutover.", references=["metadata.integration_cutover.systems"], evidence_ids=evidence_ids)
            for index, system in enumerate(systems, start=1)
        ]
        + [
            _item(f"ED{index}", dependency, "vendor_owner", f"Confirm external dependency {dependency} has an available support path and change window.", severity="high", references=["metadata.integration_cutover.external_dependencies"], evidence_ids=evidence_ids)
            for index, dependency in enumerate(external_dependencies, start=1)
        ],
        "sequencing_steps": [
            _item("SS1", "pre_cutover_snapshot", "technical_owner", "Capture configuration, data, and integration state before changes begin.", timing="T-60 minutes", evidence_ids=evidence_ids),
            _item("SS2", "enable_integration_route", "technical_owner", f"Switch traffic or credentials for {', '.join(systems)} in the approved sequence.", timing="cutover start", evidence_ids=evidence_ids),
            _item("SS3", "stabilization_watch", "release_manager", "Hold the cutover window open until validation checks pass and owners approve closure.", timing="post-switch", evidence_ids=evidence_ids),
        ],
        "validation_checks": [
            _item(f"VC{index}", metric, "qa_owner", f"Validate {metric} before declaring cutover complete.", severity="high" if strict else "medium", references=["metadata.integration_cutover.validation_metrics"], evidence_ids=evidence_ids)
            for index, metric in enumerate(metrics, start=1)
        ],
        "rollback_triggers": _rollback_triggers(strict, rollback_owner, evidence_ids),
        "communications": _communications(strict, customer_impacting, external_dependencies, evidence_ids),
        "owner_roles": _owner_roles(ctx, rollback_owner),
        "evidence_references": ctx["evidence_references"],
    }


def _rollback_triggers(strict: bool, rollback_owner: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    triggers = [
        _item("RT1", "critical_validation_failure", rollback_owner, "Rollback if a required validation check fails and cannot be corrected inside the cutover window.", severity="high", evidence_ids=evidence_ids),
        _item("RT2", "unhealthy_dependency", rollback_owner, "Rollback if a required internal or external dependency is unavailable during verification.", severity="high" if strict else "medium", evidence_ids=evidence_ids),
    ]
    if strict:
        triggers.append(_item("RT3", "customer_impact_threshold", rollback_owner, "Rollback on confirmed customer-facing outage, material data mismatch, or unresolved support escalation.", severity="critical", evidence_ids=evidence_ids))
    return triggers


def _communications(
    strict: bool, customer_impacting: bool, external_dependencies: list[str], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    audience = "customers, support, and external dependency owners" if strict else "internal cutover owners"
    return [
        _item("CM1", "pre_cutover_notice", "communications_owner", f"Send pre-cutover notice to {audience}.", timing="T-24 hours" if strict else "T-4 hours", severity="high" if customer_impacting else "medium", evidence_ids=evidence_ids),
        _item("CM2", "live_status_updates", "communications_owner", "Post cutover start, validation, rollback, and completion status updates.", timing="during cutover", severity="high" if strict else "medium", evidence_ids=evidence_ids),
        _item("CM3", "dependency_coordination", "vendor_owner", f"Keep support contacts ready for {', '.join(external_dependencies)}." if external_dependencies else "Keep internal escalation contacts ready.", timing="during cutover", evidence_ids=evidence_ids),
    ]


def _owner_roles(ctx: dict[str, Any], rollback_owner: str) -> list[dict[str, str]]:
    return [
        {"role": "release_manager", "suggested_owner": ctx["buyer"], "responsibility": "Own the cutover decision, schedule, and go/no-go approvals."},
        {"role": "technical_owner", "suggested_owner": "engineering_owner", "responsibility": "Execute sequencing steps and dependency readiness checks."},
        {"role": "rollback_owner", "suggested_owner": rollback_owner, "responsibility": "Authorize and execute rollback when triggers are met."},
        {"role": "communications_owner", "suggested_owner": "support_owner", "responsibility": "Coordinate customer, support, and stakeholder communications."},
    ]


def _hints(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get(key)
    return hints if isinstance(hints, dict) else {}


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return compact(value).lower() in {"1", "true", "yes", "y", "customer", "customer-impacting", "external"}


def _item(
    item_id: str,
    name: str,
    owner: str,
    description: str,
    *,
    severity: str = "medium",
    timing: str | None = None,
    references: list[str] | None = None,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "severity": severity,
        "timing": timing or "planned",
        "description": description,
        "references": references or [],
        "evidence_reference_ids": evidence_ids or [],
    }


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
