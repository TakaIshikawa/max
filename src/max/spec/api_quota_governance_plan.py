"""Generate deterministic API quota governance plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, markdown_header, number, string_list, text


SCHEMA_VERSION = "max-api-quota-governance-plan/v1"
KIND = "max.api_quota_governance_plan"


def generate_api_quota_governance_plan(spec_like: Any) -> dict[str, Any]:
    """Return structured API quota policy guidance and exception handling."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    consumers = _quota_policy_rows(spec)
    exceptions = _exception_queue(spec, consumers)
    enforcement = _enforcement_plan(spec, consumers)
    cadence = _monitoring_cadence(spec)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(spec),
        "summary": {
            "title": _title(spec),
            "consumer_count": len(consumers),
            "over_quota_count": sum(1 for row in consumers if row["risk_state"] == "over_quota"),
            "near_quota_count": sum(1 for row in consumers if row["risk_state"] == "near_quota"),
            "compliant_count": sum(1 for row in consumers if row["risk_state"] == "compliant"),
            "exception_count": len(exceptions),
            "monitoring_cadence": cadence["cadence"],
        },
        "quota_policy_rows": consumers,
        "exception_queue": exceptions,
        "enforcement_plan": enforcement,
        "monitoring_cadence": cadence,
        "stakeholder_owners": _stakeholder_owners(spec),
    }


def render_api_quota_governance_plan_markdown(plan: dict[str, Any]) -> str:
    """Render an API quota governance plan as stable Markdown."""
    lines = markdown_header(plan, "API Quota Governance Plan")
    _extend(lines, "Quota Summary", plan.get("quota_policy_rows") or [], _render_policy_row)
    _extend(lines, "Exception Queue", plan.get("exception_queue") or [], _render_exception)
    _extend(lines, "Enforcement Plan", plan.get("enforcement_plan") or [], _render_enforcement)
    cadence = plan.get("monitoring_cadence") if isinstance(plan.get("monitoring_cadence"), dict) else {}
    lines.extend(["## Monitoring Cadence", ""])
    lines.extend(
        [
            f"- Cadence: {text(cadence.get('cadence')) or 'weekly'}",
            f"- Metrics: {_join(cadence.get('metrics'))}",
            f"- Review owner: {text(cadence.get('review_owner')) or 'api_platform_owner'}",
            f"- Escalation: {text(cadence.get('escalation')) or 'Review sustained quota risk with stakeholder owners.'}",
            "",
        ]
    )
    _extend(lines, "Stakeholder Owners", plan.get("stakeholder_owners") or [], _render_owner)
    return "\n".join(lines).rstrip() + "\n"


def _quota_policy_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    consumers = _records(spec.get("api_consumers") or spec.get("consumers"), "consumer")
    limits = _record_map(spec.get("current_limits") or spec.get("limits"), "consumer")
    peaks = _record_map(spec.get("usage_peaks") or spec.get("peaks"), "consumer")
    owners = _owner_map(spec.get("stakeholder_owners") or spec.get("owners"))
    actions = _action_map(spec.get("enforcement_actions") or spec.get("actions"))

    names = {item["consumer"] for item in consumers} | set(limits) | set(peaks)
    if not names:
        names.add("Unspecified API consumer")

    result: list[dict[str, Any]] = []
    for name in sorted(names, key=str.casefold):
        consumer_record = next((item for item in consumers if item["consumer"] == name), {})
        limit_record = limits.get(name, {})
        peak_record = peaks.get(name, {})
        limit = number(_first(limit_record.get("limit"), limit_record.get("quota"), consumer_record.get("limit")))
        usage_peak = number(_first(peak_record.get("usage_peak"), peak_record.get("peak"), peak_record.get("usage"), consumer_record.get("usage_peak")))
        utilization = _utilization(usage_peak, limit)
        risk_state = _risk_state(utilization)
        owner = _first(consumer_record.get("owner"), owners.get(name), limit_record.get("owner"), "api_platform_owner")
        result.append(
            {
                "id": "",
                "consumer": name,
                "limit": limit,
                "usage_peak": usage_peak,
                "utilization": utilization,
                "risk_state": risk_state,
                "owner": owner,
                "action": _first(actions.get(risk_state), actions.get(name), _default_action(risk_state)),
            }
        )
    result = sorted(result, key=lambda item: (_risk_rank(item["risk_state"]), item["consumer"].casefold()))
    for index, item in enumerate(result, start=1):
        item["id"] = f"QPR{index}"
    return result


def _exception_queue(spec: dict[str, Any], policy_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owners = _owner_map(spec.get("stakeholder_owners") or spec.get("owners"))
    rows = _records(spec.get("exception_requests") or spec.get("exceptions"), "consumer")
    result: list[dict[str, Any]] = []
    for row in rows:
        consumer = row["consumer"]
        policy = next((item for item in policy_rows if item["consumer"] == consumer), {})
        requested_limit = number(_first(row.get("requested_limit"), row.get("limit")))
        current_limit = policy.get("limit")
        result.append(
            {
                "id": f"EXC{len(result) + 1}",
                "consumer": consumer,
                "requested_limit": requested_limit,
                "current_limit": current_limit,
                "status": _first(row.get("status"), "pending"),
                "justification": _first(row.get("justification"), row.get("reason"), "Not provided"),
                "owner": _first(row.get("owner"), owners.get(consumer), policy.get("owner"), "api_platform_owner"),
                "decision": _exception_decision(requested_limit, current_limit),
            }
        )
    return sorted(result, key=lambda item: (item["status"].casefold(), item["consumer"].casefold()))


def _enforcement_plan(spec: dict[str, Any], policy_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configured = _records(spec.get("enforcement_actions"), "name")
    if configured and any("consumer" not in item for item in configured):
        result = []
        for item in configured:
            risk_state = _first(item.get("risk_state"), item.get("trigger"), "near_quota")
            result.append(
                {
                    "id": f"ENF{len(result) + 1}",
                    "risk_state": risk_state,
                    "owner": _first(item.get("owner"), "api_platform_owner"),
                    "action": _first(item.get("action"), item.get("name"), _default_action(risk_state)),
                    "timing": _first(item.get("timing"), "next review"),
                }
            )
        return sorted(result, key=lambda item: (_risk_rank(item["risk_state"]), item["id"]))

    result = []
    for risk_state in ("over_quota", "near_quota", "compliant"):
        impacted = [row["consumer"] for row in policy_rows if row["risk_state"] == risk_state]
        result.append(
            {
                "id": f"ENF{len(result) + 1}",
                "risk_state": risk_state,
                "owner": "api_platform_owner",
                "action": _default_action(risk_state),
                "timing": _default_timing(risk_state),
                "consumers": impacted,
            }
        )
    return result


def _monitoring_cadence(spec: dict[str, Any]) -> dict[str, Any]:
    cadence = spec.get("monitoring_cadence") if isinstance(spec.get("monitoring_cadence"), dict) else {}
    return {
        "cadence": _first(cadence.get("cadence"), spec.get("review_cadence"), "weekly"),
        "metrics": string_list(cadence.get("metrics")) or ["quota utilization", "429 responses", "exception aging"],
        "review_owner": _first(cadence.get("review_owner"), cadence.get("owner"), "api_platform_owner"),
        "escalation": _first(cadence.get("escalation"), "Review sustained quota risk with stakeholder owners."),
    }


def _stakeholder_owners(spec: dict[str, Any]) -> list[dict[str, str]]:
    owners = _owner_map(spec.get("stakeholder_owners") or spec.get("owners"))
    return [{"consumer": consumer, "owner": owner} for consumer, owner in sorted(owners.items(), key=lambda item: item[0].casefold())]


def _records(value: Any, default_key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        record = dict(item) if isinstance(item, dict) else {default_key: item}
        consumer = compact(record.get("consumer") or record.get("name") or record.get("api_consumer"))
        if consumer:
            record["consumer"] = consumer
        name = compact(record.get("name") or record.get("risk_state") or record.get("trigger"))
        if name:
            record["name"] = name
        if consumer or name:
            result.append(record)
    return result


def _record_map(value: Any, key_field: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            record = dict(item) if isinstance(item, dict) else {"limit": item}
            result[compact(key)] = record
    elif isinstance(value, list):
        for item in value:
            record = dict(item) if isinstance(item, dict) else {key_field: item}
            key = compact(record.get(key_field) or record.get("name"))
            if key:
                result[key] = record
    return {key: item for key, item in result.items() if key}


def _owner_map(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {compact(key): compact(owner) for key, owner in value.items() if compact(key) and compact(owner)}
    if isinstance(value, list):
        return {
            compact(item.get("consumer") or item.get("name")): compact(item.get("owner"))
            for item in value
            if isinstance(item, dict) and compact(item.get("consumer") or item.get("name")) and compact(item.get("owner"))
        }
    return {}


def _action_map(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {compact(key): compact(action) for key, action in value.items() if compact(key) and compact(action)}
    if isinstance(value, list):
        result: dict[str, str] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            key = compact(item.get("risk_state") or item.get("consumer") or item.get("trigger") or item.get("name"))
            action = compact(item.get("action") or item.get("description"))
            if key and action:
                result[key] = action
        return result
    return {}


def _source(spec: dict[str, Any]) -> dict[str, Any]:
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    return {"idea_id": compact(source.get("idea_id")) or compact(spec.get("id"))}


def _title(spec: dict[str, Any]) -> str:
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    return _first(project.get("title"), spec.get("title"), "API Quota Governance")


def _utilization(usage_peak: float | None, limit: float | None) -> float | None:
    if usage_peak is None or limit is None or limit <= 0:
        return None
    return round(usage_peak / limit, 4)


def _risk_state(utilization: float | None) -> str:
    if utilization is None:
        return "unknown"
    if utilization > 1:
        return "over_quota"
    if utilization >= 0.8:
        return "near_quota"
    return "compliant"


def _risk_rank(value: str) -> int:
    return {"over_quota": 0, "near_quota": 1, "unknown": 2, "compliant": 3}.get(value, 4)


def _default_action(risk_state: str) -> str:
    return {
        "over_quota": "Throttle excess traffic and require quota exception approval.",
        "near_quota": "Notify owner and review quota trend before the next peak window.",
        "compliant": "Continue standard monitoring.",
    }.get(risk_state, "Validate missing quota telemetry.")


def _default_timing(risk_state: str) -> str:
    return {"over_quota": "immediate", "near_quota": "next business day", "compliant": "weekly review"}.get(risk_state, "next review")


def _exception_decision(requested_limit: float | None, current_limit: float | None) -> str:
    if requested_limit is None:
        return "needs_requested_limit"
    if current_limit is not None and requested_limit <= current_limit:
        return "close_as_no_increase"
    return "pending_governance_review"


def _extend(lines: list[str], title: str, items: list[Any], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_policy_row(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['consumer']}",
        "",
        f"- Limit: {text(item.get('limit')) or 'unknown'}",
        f"- Usage peak: {text(item.get('usage_peak')) or 'unknown'}",
        f"- Utilization: {_percent(item.get('utilization'))}",
        f"- Risk state: {item['risk_state']}",
        f"- Owner: {item['owner']}",
        f"- Action: {item['action']}",
    ]


def _render_exception(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['consumer']}",
        "",
        f"- Requested limit: {text(item.get('requested_limit')) or 'unknown'}",
        f"- Current limit: {text(item.get('current_limit')) or 'unknown'}",
        f"- Status: {item['status']}",
        f"- Owner: {item['owner']}",
        f"- Decision: {item['decision']}",
        f"- Justification: {item['justification']}",
    ]


def _render_enforcement(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['risk_state']}",
        "",
        f"- Owner: {item['owner']}",
        f"- Timing: {item['timing']}",
        f"- Action: {item['action']}",
        f"- Consumers: {_join(item.get('consumers'))}",
    ]


def _render_owner(item: dict[str, Any]) -> list[str]:
    return [f"### {item['consumer']}", "", f"- Owner: {item['owner']}"]


def _first(*values: Any) -> Any:
    for value in values:
        if compact(value):
            return value
    return ""


def _percent(value: Any) -> str:
    ratio = number(value)
    return "unknown" if ratio is None else f"{ratio * 100:.1f}%"


def _join(values: Any) -> str:
    items = string_list(values)
    return ", ".join(items) if items else "none"
