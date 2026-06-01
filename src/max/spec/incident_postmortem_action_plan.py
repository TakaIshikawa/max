"""Generate deterministic incident postmortem action plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.incident_postmortem_action_plan.v1"
KIND = "max.spec.incident_postmortem_action_plan"
SEVERITY_RANK = {"sev0": 0, "sev1": 1, "sev2": 2, "sev3": 3, "sev4": 4}


def generate_incident_postmortem_action_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    incident_id = _required(hints, "incident_id", "incident id")
    severity = _severity(_required(hints, "severity", "severity"))
    root_causes = _required_records(hints.get("root_causes"), "root causes")
    owners = _required_list(hints.get("owners") or hints.get("action_owners"), "action owners")
    timeline = compact(hints.get("timeline_summary")) or "timeline summary pending"
    customer_impact = compact(hints.get("customer_impact")) or "customer impact under review"
    review_date = compact(hints.get("follow_up_review_date")) or compact(hints.get("review_date")) or "not scheduled"
    refs = [item["id"] for item in ctx["evidence_references"]]

    actions = _actions(hints.get("actions") or hints.get("corrective_actions"), root_causes, owners, refs)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, incident_id=incident_id, severity=severity, action_count=len(actions)),
        "impact_summary": [{"incident_id": incident_id, "severity": severity, "timeline_summary": timeline, "customer_impact": customer_impact, "follow_up_review_date": review_date}],
        "root_cause_mapping": [_row("RC", i, cause["name"], owners[(i - 1) % len(owners)], f"Map corrective actions for root cause: {cause['name']}.", refs, category=cause.get("category")) for i, cause in enumerate(root_causes, 1)],
        "corrective_actions": actions,
        "prevention_checks": _prevention_checks(severity, refs),
        "customer_follow_up": [_row("CF", 1, "Customer follow-up", owners[0], f"Confirm customer communications and remediation for impact: {customer_impact}.", refs)],
        "review_cadence": [_row("RV", 1, "Postmortem follow-up review", owners[0], f"Review action closure on {review_date}.", refs, due_date=review_date)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("incident_postmortem_action")
    return value if isinstance(value, dict) else {}


def _required(hints: dict[str, Any], key: str, label: str) -> str:
    value = compact(hints.get(key))
    if not value:
        raise ValueError(f"incident_postmortem_action requires {label}")
    return value


def _required_list(value: Any, label: str) -> list[str]:
    values = sorted(dict.fromkeys(item for item in string_list(value) if item), key=str.casefold)
    if not values:
        raise ValueError(f"incident_postmortem_action requires {label}")
    return values


def _required_records(value: Any, label: str) -> list[dict[str, str]]:
    raw = value if isinstance(value, list) else []
    records = []
    for index, item in enumerate(raw, 1):
        if isinstance(item, dict):
            name = compact(item.get("name") or item.get("cause") or item.get("description")) or f"root cause {index}"
            records.append({"name": name, "category": compact(item.get("category"))})
        else:
            name = compact(item)
            if name:
                records.append({"name": name, "category": ""})
    if not records:
        raise ValueError(f"incident_postmortem_action requires {label}")
    return sorted(records, key=lambda item: item["name"].casefold())


def _severity(value: str) -> str:
    severity = value.casefold()
    if severity not in SEVERITY_RANK:
        raise ValueError("incident_postmortem_action requires severity sev0, sev1, sev2, sev3, or sev4")
    return severity


def _actions(value: Any, root_causes: list[dict[str, str]], owners: list[str], refs: list[str]) -> list[dict[str, Any]]:
    names = string_list(value) or [f"Prevent recurrence of {cause['name']}" for cause in root_causes]
    return [_row("CA", i, name, owners[(i - 1) % len(owners)], f"Complete corrective action: {name}.", refs, status="open") for i, name in enumerate(sorted(dict.fromkeys(names), key=str.casefold), 1)]


def _prevention_checks(severity: str, refs: list[str]) -> list[dict[str, Any]]:
    checks = ["runbook update", "monitoring validation"]
    if severity in {"sev0", "sev1"}:
        checks.extend(["executive review", "customer communication audit"])
    return [_row("PC", i, check, "incident_owner", f"Verify prevention control: {check}.", refs) for i, check in enumerate(checks, 1)]


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None)})
    return data
