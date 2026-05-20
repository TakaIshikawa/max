"""Generate deterministic SLA acceptance plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.sla_acceptance_plan.v1"
KIND = "max.spec.sla_acceptance_plan"


def generate_sla_acceptance_plan(spec_like: Any) -> dict[str, Any]:
    """Return SLA acceptance targets, measurement, gates, and breach response."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec, "sla_acceptance")
    targets = _targets(hints.get("targets") or spec.get("slas") or spec.get("slos"))
    dependencies = _values(hints.get("dependencies") or spec.get("dependencies"), [])
    monitoring = _values(hints.get("monitoring_signals") or spec.get("monitoring_signals"), [])
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, target_count=len(targets), dependency_count=len(dependencies), monitoring_signal_count=len(monitoring)),
        "acceptance_targets": targets,
        "measurement_plan": _measurement_plan(targets, monitoring, evidence_ids),
        "escalation_rules": _escalation_rules(targets, dependencies, evidence_ids),
        "approval_gates": _approval_gates(targets, monitoring, evidence_ids),
        "breach_actions": _breach_actions(targets, dependencies, evidence_ids),
        "setup_actions": _setup_actions(monitoring, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _targets(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    targets: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            name = compact(item.get("name") or item.get("metric")) or f"SLA target {index}"
            objective = compact(item.get("objective") or item.get("target") or item.get("value")) or "agreed service level"
            window = compact(item.get("window") or item.get("measurement_window")) or "30 days"
            owner = compact(item.get("owner")) or "service_owner"
        else:
            name = compact(item) or f"SLA target {index}"
            objective = "agreed service level"
            window = "30 days"
            owner = "service_owner"
        targets.append({"id": f"SLA{index}", "name": name, "objective": objective, "measurement_window": window, "owner": owner})
    return targets or [{"id": "SLA1", "name": "availability", "objective": "99.9%", "measurement_window": "30 days", "owner": "service_owner"}]


def _measurement_plan(targets: list[dict[str, Any]], monitoring: list[str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    signal = ", ".join(monitoring) if monitoring else "monitoring signal pending setup"
    return [
        {
            "id": f"MP{index}",
            "target_id": target["id"],
            "metric": target["name"],
            "window": target["measurement_window"],
            "signal": signal,
            "owner": target["owner"],
            "evidence_reference_ids": evidence_ids,
        }
        for index, target in enumerate(targets, start=1)
    ]


def _escalation_rules(targets: list[dict[str, Any]], dependencies: list[str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"ER{index}",
            "target_id": target["id"],
            "condition": f"{target['name']} misses {target['objective']} during {target['measurement_window']}",
            "owner": target["owner"],
            "action": "Escalate to incident owner, dependency owner, and customer communication owner.",
            "dependencies": dependencies,
            "evidence_reference_ids": evidence_ids,
        }
        for index, target in enumerate(targets, start=1)
    ]


def _approval_gates(targets: list[dict[str, Any]], monitoring: list[str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"AG{index}",
            "target_id": target["id"],
            "owner": target["owner"],
            "approval_signal": f"{target['name']} measurement is wired and can prove {target['objective']}.",
            "status": "ready" if monitoring else "setup_required",
            "evidence_reference_ids": evidence_ids,
        }
        for index, target in enumerate(targets, start=1)
    ]


def _breach_actions(targets: list[dict[str, Any]], dependencies: list[str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"BA{index}",
            "target_id": target["id"],
            "owner": target["owner"],
            "action": f"Open breach review, preserve measurements, notify stakeholders, and remediate {target['name']} below {target['objective']}.",
            "dependency_review_required": bool(dependencies),
            "evidence_reference_ids": evidence_ids,
        }
        for index, target in enumerate(targets, start=1)
    ]


def _setup_actions(monitoring: list[str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    if monitoring:
        return []
    return [
        {
            "id": "SA1",
            "type": "monitoring_setup",
            "owner": "observability_owner",
            "action": "Create monitoring signals before SLA acceptance approval.",
            "evidence_reference_ids": evidence_ids,
        }
    ]


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _hints(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get(key)
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
