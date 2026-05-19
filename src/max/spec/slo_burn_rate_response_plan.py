"""Generate deterministic SLO burn-rate response plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, markdown_header, string_list, text


SCHEMA_VERSION = "max-slo-burn-rate-response-plan/v1"
KIND = "max.slo_burn_rate_response_plan"


def generate_slo_burn_rate_response_plan(spec_like: Any) -> dict[str, Any]:
    """Return stable SLO burn-rate response guidance for a service."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = _context(spec)
    windows = _burn_rate_windows(spec)
    thresholds = _alert_thresholds(spec)
    actions = _response_actions(spec, thresholds)
    owners = _owners(spec)
    evidence = _evidence(spec)
    classification = _classification(windows, thresholds)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": ctx["title"],
            "service": ctx["service"],
            "slo_target": ctx["slo_target"],
            "classification": classification,
            "window_count": len(windows),
            "threshold_count": len(thresholds),
            "response_action_count": len(actions),
            "customer_impact_count": len(ctx["customer_impact_notes"]),
        },
        "service_targets": ctx["service_targets"],
        "burn_rate_windows": windows,
        "alert_thresholds": thresholds,
        "response_actions": actions,
        "owners": owners,
        "customer_impact": ctx["customer_impact_notes"],
        "evidence": evidence,
    }


def render_slo_burn_rate_response_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a burn-rate response plan as deterministic Markdown."""
    lines = markdown_header(plan, "SLO Burn-Rate Response Plan")
    _extend(lines, "Service Targets", plan.get("service_targets") or [], _render_target)
    _extend(lines, "Burn-Rate Windows", plan.get("burn_rate_windows") or [], _render_window)
    _extend(lines, "Alert Thresholds", plan.get("alert_thresholds") or [], _render_threshold)
    _extend(lines, "Escalation Steps", plan.get("response_actions") or [], _render_action)
    _extend(lines, "Owners", plan.get("owners") or [], _render_owner)
    _extend(lines, "Customer Impact", plan.get("customer_impact") or [], _render_impact)
    _extend(lines, "Evidence", plan.get("evidence") or [], _render_evidence)
    return "\n".join(lines).rstrip() + "\n"


def _context(spec: dict[str, Any]) -> dict[str, Any]:
    project = _section(spec, "project")
    service = _section(spec, "service")
    slo_targets = spec.get("slo_targets") or service.get("slo_targets") or service.get("slos")
    targets = _service_targets(slo_targets, service)
    return {
        "title": _first(project.get("title"), service.get("name"), spec.get("title"), "Unknown"),
        "service": _first(service.get("name"), spec.get("service_name"), spec.get("service"), "Unknown"),
        "slo_target": targets[0]["target"] if targets else "Unknown",
        "service_targets": targets,
        "customer_impact_notes": _items(spec.get("customer_impact_notes") or service.get("customer_impact_notes")),
    }


def _service_targets(value: Any, service: dict[str, Any]) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        item = row if isinstance(row, dict) else {"name": row}
        name = _first(item.get("name"), item.get("slo"), f"slo_{index}")
        result.append(
            {
                "id": f"SLO{len(result) + 1}",
                "name": name,
                "target": _first(item.get("target"), item.get("objective"), service.get("slo_target"), "99.9%"),
                "indicator": _first(item.get("indicator"), item.get("metric"), "availability"),
                "owner": _first(item.get("owner"), service.get("owner"), "slo_owner"),
            }
        )
    if not result:
        result.append(
            {
                "id": "SLO1",
                "name": _first(service.get("slo_name"), "availability"),
                "target": _first(service.get("slo_target"), "99.9%"),
                "indicator": _first(service.get("indicator"), "availability"),
                "owner": _first(service.get("owner"), "slo_owner"),
            }
        )
    return sorted(result, key=lambda item: (item["name"].casefold(), item["id"]))


def _burn_rate_windows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    values = spec.get("burn_rate_windows")
    rows = values if isinstance(values, list) else []
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        item = row if isinstance(row, dict) else {"window": row}
        burn_rate = _number(item.get("burn_rate"))
        result.append(
            {
                "id": f"BRW{index}",
                "window": _first(item.get("window"), item.get("duration"), "Unknown"),
                "burn_rate": burn_rate,
                "classification": _burn_classification(burn_rate),
                "exhaustion_eta": _first(item.get("exhaustion_eta"), item.get("eta"), "not forecast"),
                "evidence_refs": _items(item.get("evidence_refs")),
            }
        )
    return sorted(result, key=lambda item: (_classification_rank(item["classification"]), item["window"]))


def _alert_thresholds(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = spec.get("alert_thresholds") if isinstance(spec.get("alert_thresholds"), list) else []
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        item = row if isinstance(row, dict) else {"name": row}
        severity = _severity(item.get("severity"), _number(item.get("burn_rate")))
        result.append(
            {
                "id": f"ALT{index}",
                "name": _first(item.get("name"), item.get("window"), f"threshold_{index}"),
                "window": _first(item.get("window"), "Unknown"),
                "burn_rate": _number(item.get("burn_rate")),
                "severity": severity,
                "condition": _first(item.get("condition"), f"burn rate reaches {text(item.get('burn_rate')) or 'configured'}x"),
                "owner": _first(item.get("owner"), "on_call_owner"),
            }
        )
    return sorted(result, key=lambda item: (_severity_rank(item["severity"]), item["window"], item["name"]))


def _response_actions(spec: dict[str, Any], thresholds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = spec.get("escalation_actions") if isinstance(spec.get("escalation_actions"), list) else []
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        item = row if isinstance(row, dict) else {"action": row}
        severity = _first(item.get("severity"), item.get("trigger"), thresholds[0]["severity"] if thresholds else "warning")
        result.append(
            {
                "id": f"ACT{index}",
                "name": _first(item.get("name"), f"{severity}_response"),
                "severity": severity,
                "owner": _first(item.get("owner"), "incident_commander"),
                "timing": _first(item.get("timing"), item.get("within"), "immediate"),
                "action": _first(item.get("action"), item.get("description"), "Assess burn-rate alert and coordinate response."),
            }
        )
    if not result:
        result.append(
            {
                "id": "ACT1",
                "name": "initial_triage",
                "severity": "warning",
                "owner": "on_call_owner",
                "timing": "15 minutes",
                "action": "Confirm error-budget burn source, customer scope, and rollback readiness.",
            }
        )
    return sorted(result, key=lambda item: (_severity_rank(item["severity"]), item["id"]))


def _owners(spec: dict[str, Any]) -> list[dict[str, str]]:
    owners = spec.get("owners") if isinstance(spec.get("owners"), dict) else {}
    if not owners:
        return [{"role": "on_call_owner", "owner": "Unassigned"}, {"role": "incident_commander", "owner": "Unassigned"}]
    return [{"role": compact(role), "owner": compact(owner)} for role, owner in sorted(owners.items()) if compact(role)]


def _evidence(spec: dict[str, Any]) -> list[dict[str, str]]:
    refs = evidence_references(spec)
    if refs:
        return refs
    return [{"id": "EV1", "type": "operational", "reference": item} for item in _items(spec.get("evidence"))]


def _classification(windows: list[dict[str, Any]], thresholds: list[dict[str, Any]]) -> str:
    labels = [item["classification"] for item in windows] + [item["severity"] for item in thresholds]
    if "critical" in labels:
        return "critical"
    if "warning" in labels:
        return "warning"
    return "healthy"


def _burn_classification(burn_rate: float | None) -> str:
    if burn_rate is None or burn_rate < 1:
        return "healthy"
    if burn_rate < 2:
        return "warning"
    return "critical"


def _severity(value: Any, burn_rate: float | None) -> str:
    label = compact(value).lower()
    if label in {"healthy", "warning", "critical"}:
        return label
    return _burn_classification(burn_rate)


def _classification_rank(value: str) -> int:
    return {"critical": 0, "warning": 1, "healthy": 2}.get(value, 3)


def _severity_rank(value: str) -> int:
    return _classification_rank(value)


def _extend(lines: list[str], title: str, items: list[Any], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_target(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Target: {item['target']}", f"- Indicator: {item['indicator']}", f"- Owner: {item['owner']}"]


def _render_window(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['window']}", "", f"- Burn rate: {text(item['burn_rate']) or 'unknown'}x", f"- Classification: {item['classification']}", f"- Exhaustion ETA: {item['exhaustion_eta']}"]


def _render_threshold(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Window: {item['window']}", f"- Severity: {item['severity']}", f"- Condition: {item['condition']}", f"- Owner: {item['owner']}"]


def _render_action(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Severity: {item['severity']}", f"- Owner: {item['owner']}", f"- Timing: {item['timing']}", f"- Action: {item['action']}"]


def _render_owner(item: dict[str, Any]) -> list[str]:
    return [f"### {item['role']}", "", f"- Owner: {item['owner']}"]


def _render_impact(item: str) -> list[str]:
    return [f"- {item}"]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Type: {item['type']}", f"- Reference: {item['reference']}"]


def _section(spec: dict[str, Any], name: str) -> dict[str, Any]:
    value = spec.get(name)
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[str]:
    return sorted(dict.fromkeys(string_list(value)), key=str.casefold)


def _first(*values: Any) -> str:
    for value in values:
        result = compact(value)
        if result:
            return result
    return "Unknown"


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
