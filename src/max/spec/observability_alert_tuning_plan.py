"""Generate deterministic observability alert tuning plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, markdown_header, string_list


SCHEMA_VERSION = "max-observability-alert-tuning-plan/v1"
KIND = "max.observability_alert_tuning_plan"


def generate_observability_alert_tuning_plan(spec_like: Any) -> dict[str, Any]:
    """Return stable alert tuning recommendations from an alert inventory."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    alerts = _alerts(spec.get("alerts") or spec.get("alert_inventory"))
    noisy = [alert for alert in alerts if alert["classification"] == "noisy"]
    missing = _missing_alerts(spec)
    thresholds = [alert for alert in alerts if alert["recommended_change"] == "threshold_update"]
    cadence = _first(spec.get("review_cadence"), "weekly during rollout; monthly after stabilization")

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _title(spec),
            "alert_count": len(alerts),
            "noisy_alert_count": len(noisy),
            "coverage_gap_count": len(missing),
            "threshold_update_count": len(thresholds),
            "review_cadence": cadence,
        },
        "alert_classifications": alerts,
        "noisy_alerts": noisy,
        "coverage_gaps": missing,
        "threshold_updates": thresholds,
        "owners": _owners(spec, alerts, missing),
        "review_cadence": cadence,
        "rollout_safeguards": _items(spec.get("rollout_safeguards") or ["shadow tuned thresholds for one week", "keep rollback path for alert rules"]),
        "evidence": evidence_references(spec),
    }


def render_observability_alert_tuning_plan_markdown(plan: dict[str, Any]) -> str:
    """Render an alert tuning plan as deterministic Markdown."""
    lines = markdown_header(plan, "Observability Alert Tuning Plan")
    _extend(lines, "Noisy Alerts", plan.get("noisy_alerts") or [], _render_alert)
    _extend(lines, "Coverage Gaps", plan.get("coverage_gaps") or [], _render_gap)
    _extend(lines, "Threshold Updates", plan.get("threshold_updates") or [], _render_alert)
    _extend(lines, "Owner Review Cadence", [{"id": "CAD1", "cadence": plan.get("review_cadence")}], _render_cadence)
    _extend(lines, "Rollout Validation", plan.get("rollout_safeguards") or [], _render_text)
    _extend(lines, "Evidence", plan.get("evidence") or [], _render_evidence)
    return "\n".join(lines).rstrip() + "\n"


def _alerts(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    merged: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, start=1):
        item = row if isinstance(row, dict) else {"name": row}
        name = _first(item.get("name"), f"alert_{index}")
        existing = merged.get(name.casefold())
        candidate = _alert(item, name, index)
        if existing is None or _severity_rank(candidate["severity"]) < _severity_rank(existing["severity"]):
            merged[name.casefold()] = candidate
        elif existing is not None:
            existing["duplicate_count"] += 1
    result = list(merged.values())
    return sorted(result, key=lambda item: (_severity_rank(item["severity"]), item["name"].casefold()))


def _alert(item: dict[str, Any], name: str, index: int) -> dict[str, Any]:
    pages = _number(item.get("page_count") or item.get("pages_per_week"))
    actionable = _number(item.get("actionable_rate"))
    missing_signal = bool(item.get("missing_signal"))
    classification = "coverage_gap" if missing_signal else "noisy" if pages >= 10 or actionable < 0.3 else "healthy"
    change = item.get("recommended_change")
    if not change:
        change = "add_alert" if classification == "coverage_gap" else "threshold_update" if classification == "noisy" else "keep"
    return {
        "id": f"ALT{index}",
        "name": name,
        "severity": _severity(item.get("severity")),
        "classification": classification,
        "recommended_change": compact(change),
        "owner": _first(item.get("owner"), "observability_owner"),
        "condition": _first(item.get("condition"), "configured alert condition"),
        "action": _first(item.get("action"), _default_action(classification)),
        "duplicate_count": 1,
    }


def _missing_alerts(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = spec.get("missing_alerts") or spec.get("coverage_gaps")
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows if isinstance(rows, list) else [], start=1):
        item = row if isinstance(row, dict) else {"name": row}
        result.append(
            {
                "id": f"GAP{index}",
                "name": _first(item.get("name"), f"gap_{index}"),
                "severity": _severity(item.get("severity")),
                "owner": _first(item.get("owner"), "observability_owner"),
                "description": _first(item.get("description"), "Missing alert coverage."),
                "recommended_change": "add_alert",
            }
        )
    return sorted(result, key=lambda item: (_severity_rank(item["severity"]), item["name"].casefold()))


def _owners(spec: dict[str, Any], alerts: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> list[dict[str, str]]:
    explicit = spec.get("owners") if isinstance(spec.get("owners"), dict) else {}
    rows = [{"role": compact(role), "owner": compact(owner)} for role, owner in sorted(explicit.items()) if compact(role)]
    seen = {row["role"] for row in rows}
    for item in alerts + gaps:
        owner = compact(item.get("owner"))
        if owner and owner not in seen:
            rows.append({"role": owner, "owner": owner})
            seen.add(owner)
    return rows or [{"role": "observability_owner", "owner": "Unassigned"}]


def _render_alert(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['name']}",
        "",
        f"- Severity: {item['severity']}",
        f"- Classification: {item['classification']}",
        f"- Recommended change: {item['recommended_change']}",
        f"- Owner: {item['owner']}",
        f"- Condition: {item['condition']}",
        f"- Action: {item['action']}",
        f"- Duplicate count: {item['duplicate_count']}",
    ]


def _render_gap(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Severity: {item['severity']}", f"- Owner: {item['owner']}", f"- Description: {item['description']}", f"- Recommended change: {item['recommended_change']}"]


def _render_cadence(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Cadence: {item['cadence']}"]


def _render_text(item: str) -> list[str]:
    return [f"- {item}"]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Type: {item['type']}", f"- Reference: {item['reference']}"]


def _extend(lines: list[str], title: str, items: list[Any], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _title(spec: dict[str, Any]) -> str:
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    return _first(project.get("title"), spec.get("title"), "Alert Tuning")


def _severity(value: Any) -> str:
    label = compact(value).lower()
    return label if label in {"critical", "warning", "info"} else "warning"


def _severity_rank(value: str) -> int:
    return {"critical": 0, "warning": 1, "info": 2}.get(value, 3)


def _default_action(classification: str) -> str:
    if classification == "noisy":
        return "Raise threshold, add suppression, or convert to ticket during validation."
    if classification == "coverage_gap":
        return "Add alert before rollout expands."
    return "Keep alert and review on cadence."


def _items(value: Any) -> list[str]:
    return sorted(dict.fromkeys(string_list(value)), key=str.casefold)


def _first(*values: Any) -> str:
    for value in values:
        result = compact(value)
        if result:
            return result
    return "Unknown"


def _number(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
