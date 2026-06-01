"""Generate deterministic data residency exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list
from max.spec._review_plan_common import evidence_ids, row, source_summary


SCHEMA_VERSION = "max.spec.data_residency_exception_plan.v1"
KIND = "max.spec.data_residency_exception_plan"


def generate_data_residency_exception_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    evidence = evidence_ids(ctx)

    region = _required(hints, ("region", "affected_region", "residency_region"), "region")
    owner = _required(hints, ("owner", "requesting_owner", "request_owner"), "owner")
    expiry = _required(hints, ("expiry_date", "expiry", "expiration_date", "expiration"), "expiry_date")
    data_classes = _required_list(hints, ("data_classes", "customer_data_classes", "data_class"), "data_classes")
    controls = _required_list(hints, ("compensating_controls", "controls"), "compensating_controls")
    approvers = _required_list(hints, ("review_approvers", "approvers", "approvals"), "review_approvers")

    request = compact(hints.get("request") or hints.get("exception") or hints.get("name")) or f"{region} residency exception"
    customers = _list(hints, ("customers", "customer_cohorts"), ["affected customers"])
    monitors = _list(hints, ("monitoring", "monitors"), ["regional transfer monitoring", "customer impact review"])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, region=region, requesting_owner=owner, expiry_date=expiry, data_class_count=len(data_classes)),
        "exception_scope": [
            row(
                "DRE",
                1,
                request,
                owner,
                f"Time-boxed exception for {region} covering {', '.join(data_classes)} until {expiry}.",
                evidence,
                region=region,
                data_classes=data_classes,
                customers=customers,
                expiry=expiry,
                severity=compact(hints.get("severity")) or "high",
            )
        ],
        "risk_controls": [
            row("DRC", index, control, owner, f"Operate compensating control for {region}: {control}.", evidence, status="required")
            for index, control in enumerate(controls, start=1)
        ],
        "approval_workflow": [
            row("DRA", index, approver, approver, f"Approve residency exception scope, controls, and expiry date {expiry}.", evidence, status="pending")
            for index, approver in enumerate(approvers, start=1)
        ],
        "monitoring_tasks": [
            row("DRM", index, monitor, owner, f"Monitor exception use for {region}: {monitor}.", evidence, cadence="weekly")
            for index, monitor in enumerate(monitors, start=1)
        ],
        "expiry_review_checkpoints": [
            row("DRX", 1, "Renewal decision", owner, f"Decide whether the exception must be renewed before {expiry}.", evidence, expiry=expiry),
            row("DRX", 2, "Closure verification", owner, "Verify regional processing is restored and temporary copies are purged.", evidence, expiry=expiry),
        ],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("data_residency_exception")
    return value if isinstance(value, dict) else {}


def _required(hints: dict[str, Any], keys: tuple[str, ...], label: str) -> str:
    value = next((compact(hints.get(key)) for key in keys if compact(hints.get(key))), "")
    if not value:
        raise ValueError(f"data_residency_exception requires {label}")
    return value


def _required_list(hints: dict[str, Any], keys: tuple[str, ...], label: str) -> list[str]:
    values = _list(hints, keys, [])
    if not values:
        raise ValueError(f"data_residency_exception requires {label}")
    return values


def _list(hints: dict[str, Any], keys: tuple[str, ...], fallback: list[str]) -> list[str]:
    value = next((hints[key] for key in keys if key in hints), None)
    items = string_list(value)
    if not items and isinstance(value, list):
        items = [
            compact(item.get("name") or item.get("data_class") or item.get("customer") or item.get("description"))
            if isinstance(item, dict)
            else compact(item)
            for item in value
        ]
    return sorted(dict.fromkeys(item for item in items if item), key=str.casefold) or fallback
