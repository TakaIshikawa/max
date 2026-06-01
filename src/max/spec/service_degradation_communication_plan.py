"""Generate deterministic service degradation communication plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.service_degradation_communication_plan.v1"
KIND = "max.spec.service_degradation_communication_plan"


def generate_service_degradation_communication_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    service = _required(hints, "service_name", "service name")
    severity = _required(hints, "severity", "severity").lower()
    customers = _required_list(hints.get("affected_customers"), "affected customers")
    owner = _required(hints, "status_page_owner", "status page owner")
    channels = _required_list(hints.get("message_channels"), "message channels")
    cadence = _required(hints, "update_cadence", "update cadence")
    resolution = _required(hints, "resolution_criteria", "resolution criteria")
    refs = [item["id"] for item in ctx["evidence_references"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, service_name=service, severity=severity, affected_customer_count=len(customers), update_cadence=cadence),
        "initial_notice": [_row("SDN", 1, f"{service} initial notice", owner, f"Publish {severity} degradation notice for {service} to {', '.join(customers)}.", refs, channels=channels)],
        "update_schedule": [_row("SDU", i, channel, owner, f"Send {severity} updates every {cadence} through {channel}.", refs, cadence=cadence, severity=severity) for i, channel in enumerate(channels, 1)],
        "internal_coordination": [_row("SDI", 1, f"{service} coordination", owner, "Coordinate support, incident command, and customer-facing status before each update.", refs, affected_customers=customers)],
        "resolution_notice": [_row("SDR", 1, f"{service} resolution notice", owner, f"Publish resolution once criteria are met: {resolution}.", refs, resolution_criteria=resolution, channels=channels)],
        "post_resolution_follow_up": [_row("SDF", 1, f"{service} follow-up", owner, "Share customer follow-up, incident summary, and prevention actions after resolution.", refs, timing=_follow_up_timing(severity))],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("service_degradation_communication")
    return value if isinstance(value, dict) else {}


def _required(hints: dict[str, Any], key: str, label: str) -> str:
    value = compact(hints.get(key))
    if not value or hints.get(key) in ([], {}):
        raise ValueError(f"service_degradation_communication requires {label}")
    return value


def _required_list(value: Any, label: str) -> list[str]:
    values = sorted(dict.fromkeys(item for item in string_list(value) if item), key=str.casefold)
    if not values:
        raise ValueError(f"service_degradation_communication requires {label}")
    return values


def _follow_up_timing(severity: str) -> str:
    return "within 1 business day" if severity in {"sev1", "critical", "high"} else "within 3 business days"


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None, [])})
    return data
