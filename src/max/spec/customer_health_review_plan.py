"""Generate deterministic customer health review plans."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from max.spec._planning_common import compact, markdown_header, number, string_list, text


SCHEMA_VERSION = "max-customer-health-review-plan/v1"
KIND = "max.customer_health_review_plan"


def generate_customer_health_review_plan(spec_like: Any) -> dict[str, Any]:
    """Return structured customer health rows and review planning guidance."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    cadence = _review_cadence(spec)
    rows = _customer_health_rows(spec, cadence)
    at_risk = [row for row in rows if row["risk_state"] in {"critical", "watch"}]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(spec),
        "summary": {
            "title": _title(spec),
            "customer_count": len(rows),
            "critical_count": sum(1 for row in rows if row["risk_state"] == "critical"),
            "watch_count": sum(1 for row in rows if row["risk_state"] == "watch"),
            "healthy_count": sum(1 for row in rows if row["risk_state"] == "healthy"),
            "review_cadence": cadence["cadence"],
        },
        "customer_health_rows": rows,
        "at_risk_accounts": at_risk,
        "intervention_plan": _intervention_plan(rows),
        "review_cadence": cadence,
    }


def render_customer_health_review_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a customer health review plan as deterministic Markdown."""
    lines = markdown_header(plan, "Customer Health Review Plan")
    _extend(lines, "Health Summary", plan.get("customer_health_rows") or [], _render_health_row)
    _extend(lines, "At-Risk Accounts", plan.get("at_risk_accounts") or [], _render_at_risk)
    _extend(lines, "Intervention Plan", plan.get("intervention_plan") or [], _render_intervention)
    cadence = plan.get("review_cadence") if isinstance(plan.get("review_cadence"), dict) else {}
    lines.extend(["## Review Cadence", ""])
    lines.extend(
        [
            f"- Cadence: {text(cadence.get('cadence')) or 'monthly'}",
            f"- Anchor date: {text(cadence.get('anchor_date')) or 'not set'}",
            f"- Owner: {text(cadence.get('owner')) or 'customer_success_owner'}",
            f"- Meeting format: {text(cadence.get('meeting_format')) or 'health review'}",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _customer_health_rows(spec: dict[str, Any], cadence: dict[str, Any]) -> list[dict[str, Any]]:
    segments = _records(spec.get("customer_segments") or spec.get("segments"), "segment")
    signals = _record_map(spec.get("health_signals") or spec.get("signals"))
    drivers = _driver_map(spec.get("risk_drivers") or spec.get("drivers"))
    owners = _owner_map(spec.get("review_owners") or spec.get("owners"))
    actions = _action_map(spec.get("intervention_actions") or spec.get("actions"))

    policy_keys = {"critical", "watch", "healthy", "unknown"}
    names = {item["segment"] for item in segments} | set(signals) | set(drivers) | set(owners) | (set(actions) - policy_keys)
    if not names:
        names.add("Unspecified customer segment")

    result: list[dict[str, Any]] = []
    for segment in sorted(names, key=str.casefold):
        segment_record = next((item for item in segments if item["segment"] == segment), {})
        signal_record = signals.get(segment, {})
        score = _score(_first(signal_record.get("score"), signal_record.get("health_score"), segment_record.get("score")))
        risk_state = _risk_state(score, drivers.get(segment, []))
        result.append(
            {
                "id": "",
                "segment": segment,
                "score": score,
                "risk_state": risk_state,
                "risk_drivers": drivers.get(segment, []),
                "owner": _first(segment_record.get("owner"), owners.get(segment), "customer_success_owner"),
                "intervention": _first(actions.get(segment), actions.get(risk_state), _default_intervention(risk_state)),
                "next_review_date": _next_review_date(segment_record, signal_record, cadence, risk_state),
            }
        )
    result = sorted(result, key=lambda item: ((item["score"] if item["score"] is not None else 101), _risk_rank(item["risk_state"]), item["segment"].casefold()))
    for index, item in enumerate(result, start=1):
        item["id"] = f"CHR{index}"
    return result


def _intervention_plan(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": f"INT{len(result) + 1}",
                "segment": row["segment"],
                "risk_state": row["risk_state"],
                "owner": row["owner"],
                "intervention": row["intervention"],
                "next_review_date": row["next_review_date"],
            }
        )
    return result


def _review_cadence(spec: dict[str, Any]) -> dict[str, Any]:
    cadence = spec.get("review_cadence") if isinstance(spec.get("review_cadence"), dict) else {}
    return {
        "cadence": _first(cadence.get("cadence"), spec.get("cadence"), "monthly"),
        "anchor_date": _first(cadence.get("anchor_date"), spec.get("anchor_date"), "2026-01-01"),
        "owner": _first(cadence.get("owner"), "customer_success_owner"),
        "meeting_format": _first(cadence.get("meeting_format"), "segment health review"),
    }


def _records(value: Any, default_key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        record = dict(item) if isinstance(item, dict) else {default_key: item}
        key = compact(record.get(default_key) or record.get("name") or record.get("customer") or record.get("account"))
        if key:
            record[default_key] = key
            result.append(record)
    return result


def _record_map(value: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            result[compact(key)] = dict(item) if isinstance(item, dict) else {"score": item}
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            key = compact(item.get("segment") or item.get("name") or item.get("customer") or item.get("account"))
            if key:
                result[key] = dict(item)
    return {key: item for key, item in result.items() if key}


def _driver_map(value: Any) -> dict[str, list[str]]:
    if isinstance(value, dict):
        return {compact(key): string_list(drivers) for key, drivers in value.items() if compact(key)}
    if isinstance(value, list):
        result: dict[str, list[str]] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            key = compact(item.get("segment") or item.get("name") or item.get("customer") or item.get("account"))
            if key:
                result[key] = string_list(item.get("drivers") or item.get("risk_drivers") or item.get("driver"))
        return result
    return {}


def _owner_map(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {compact(key): compact(owner) for key, owner in value.items() if compact(key) and compact(owner)}
    if isinstance(value, list):
        return {
            compact(item.get("segment") or item.get("name") or item.get("customer") or item.get("account")): compact(item.get("owner"))
            for item in value
            if isinstance(item, dict)
            and compact(item.get("segment") or item.get("name") or item.get("customer") or item.get("account"))
            and compact(item.get("owner"))
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
            key = compact(item.get("segment") or item.get("risk_state") or item.get("name"))
            action = compact(item.get("intervention") or item.get("action"))
            if key and action:
                result[key] = action
        return result
    return {}


def _score(value: Any) -> float | None:
    score = number(value)
    if score is None:
        return None
    return max(0.0, min(100.0, score))


def _risk_state(score: float | None, drivers: list[str]) -> str:
    driver_text = " ".join(drivers).lower()
    severe_driver = any(term in driver_text for term in ("churn", "blocked", "escalation", "no adoption", "renewal risk"))
    if score is None:
        return "watch" if drivers else "unknown"
    if score < 50 or severe_driver:
        return "critical"
    if score < 75 or drivers:
        return "watch"
    return "healthy"


def _next_review_date(segment_record: dict[str, Any], signal_record: dict[str, Any], cadence: dict[str, Any], risk_state: str) -> str:
    explicit = _first(segment_record.get("next_review_date"), signal_record.get("next_review_date"))
    if explicit:
        return compact(explicit)
    anchor = _parse_date(cadence.get("anchor_date")) or date(2026, 1, 1)
    days = {"critical": 7, "watch": 14, "healthy": 30}.get(risk_state, 30)
    return (anchor + timedelta(days=days)).isoformat()


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(compact(value))
    except ValueError:
        return None


def _source(spec: dict[str, Any]) -> dict[str, str]:
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    return {"idea_id": compact(source.get("idea_id")) or compact(spec.get("id"))}


def _title(spec: dict[str, Any]) -> str:
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    return _first(project.get("title"), spec.get("title"), "Customer Health Review")


def _default_intervention(risk_state: str) -> str:
    return {
        "critical": "Schedule executive recovery review and unblock adoption risks.",
        "watch": "Assign success follow-up and verify risk driver trend.",
        "healthy": "Confirm expansion or advocacy opportunity during standard review.",
    }.get(risk_state, "Collect missing health telemetry before the next review.")


def _risk_rank(value: str) -> int:
    return {"critical": 0, "watch": 1, "unknown": 2, "healthy": 3}.get(value, 4)


def _extend(lines: list[str], title: str, items: list[Any], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_health_row(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['segment']}",
        "",
        f"- Score: {text(item.get('score')) or 'unknown'}",
        f"- Risk state: {item['risk_state']}",
        f"- Risk drivers: {_join(item.get('risk_drivers'))}",
        f"- Owner: {item['owner']}",
        f"- Intervention: {item['intervention']}",
        f"- Next review date: {item['next_review_date']}",
    ]


def _render_at_risk(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['segment']}",
        "",
        f"- Score: {text(item.get('score')) or 'unknown'}",
        f"- Risk state: {item['risk_state']}",
        f"- Risk drivers: {_join(item.get('risk_drivers'))}",
        f"- Owner: {item['owner']}",
        f"- Next review date: {item['next_review_date']}",
    ]


def _render_intervention(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['segment']}",
        "",
        f"- Risk state: {item['risk_state']}",
        f"- Owner: {item['owner']}",
        f"- Intervention: {item['intervention']}",
        f"- Next review date: {item['next_review_date']}",
    ]


def _first(*values: Any) -> Any:
    for value in values:
        if compact(value):
            return value
    return ""


def _join(values: Any) -> str:
    items = string_list(values)
    return ", ".join(items) if items else "none"
