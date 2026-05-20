"""Generate deterministic production support transition plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-production-support-transition-plan/v1"
KIND = "max.spec.production_support_transition_plan"


def generate_production_support_transition_plan(unit: Any, evaluation: Any | None = None, tact_spec_preview: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = tact_spec_preview if isinstance(tact_spec_preview, dict) else {}
    risks = _risks(unit, evaluation, spec)
    scope = _support_scope(unit, spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(unit, spec),
        "support_scope": scope,
        "owner_matrix": _owner_matrix(unit, scope),
        "triage_rules": _triage_rules(risks),
        "known_risks": risks,
        "runbook_links": _runbook_links(spec),
        "readiness_gates": _readiness_gates(evaluation, risks),
        "review_cadence": _review_cadence(),
    }


def render_production_support_transition_plan_markdown(plan: dict[str, Any]) -> str:
    lines = _header(plan, "Production Support Transition Plan")
    _extend(lines, "Support Scope", plan.get("support_scope") or [], lambda item: [f"- {item['id']}: {item['area']} coverage={item['coverage']}"])
    _extend(lines, "Owner Matrix", plan.get("owner_matrix") or [], lambda item: [f"- {item['id']}: {item['role']} owner={item['owner']}"])
    _extend(lines, "Triage Rules", plan.get("triage_rules") or [], lambda item: [f"- {item['id']}: {item['severity']} route={item['route_to']} response={item['response_time']}"])
    _extend(lines, "Readiness Gates", plan.get("readiness_gates") or [], lambda item: [f"- {item['id']}: {item['gate']} blocking={item['blocking']}"])
    return "\n".join(lines).rstrip() + "\n"


def _support_scope(unit: Any, spec: dict[str, Any]) -> list[dict[str, str]]:
    seeds = _values(_field(unit, "workflow_context")) + _values(_field(unit, "solution")) + _list(spec, "execution", "mvp_scope")
    seeds = seeds or ["primary production workflow"]
    return [{"id": f"PST-S{index}", "area": item, "coverage": "business-hours with launch hypercare", "handoff_artifact": "support runbook"} for index, item in enumerate(_dedupe(seeds)[:4], start=1)]


def _owner_matrix(unit: Any, scope: list[dict[str, str]]) -> list[dict[str, str]]:
    owners = [("support_owner", "support lead"), ("product_owner", _first(_field(unit, "buyer"), "product sponsor")), ("technical_owner", "engineering owner")]
    return [{"id": f"PST-O{index}", "role": role, "owner": owner, "scope": scope[0]["area"] if scope else "production workflow"} for index, (role, owner) in enumerate(owners, start=1)]


def _triage_rules(risks: list[dict[str, str]]) -> list[dict[str, str]]:
    strict = any(item["severity"] == "high" for item in risks)
    return [
        {"id": "PST-T1", "severity": "sev1", "condition": "customer-impacting outage or data risk", "route_to": "support_owner", "response_time": "15 minutes" if strict else "30 minutes"},
        {"id": "PST-T2", "severity": "sev2", "condition": "degraded workflow or blocked customer", "route_to": "technical_owner", "response_time": "1 hour"},
        {"id": "PST-T3", "severity": "sev3", "condition": "how-to or non-blocking defect", "route_to": "product_owner", "response_time": "next business day"},
    ]


def _risks(unit: Any, evaluation: Any | None, spec: dict[str, Any]) -> list[dict[str, str]]:
    score = _number(_field(evaluation, "overall_score"))
    seeds = _values(_field(unit, "domain_risks")) + _values(_field(evaluation, "weaknesses")) + _list(spec, "execution", "risks")
    if not seeds:
        seeds = ["handoff knowledge gaps"]
    severity = "high" if score is not None and score < 60 else "medium"
    return [{"id": f"PST-R{index}", "risk": item, "severity": severity if index == 1 else "medium", "mitigation": "assign owner and verify runbook coverage"} for index, item in enumerate(_dedupe(seeds)[:5], start=1)]


def _runbook_links(spec: dict[str, Any]) -> list[dict[str, str]]:
    links = _list(spec, "operations", "runbooks") or ["runbook-placeholder"]
    return [{"id": f"PST-B{index}", "label": item, "url": item if item.startswith("http") else "pending"} for index, item in enumerate(links, start=1)]


def _readiness_gates(evaluation: Any | None, risks: list[dict[str, str]]) -> list[dict[str, Any]]:
    strict = any(item["severity"] == "high" for item in risks) or (_number(_field(evaluation, "overall_score")) or 100) < 60
    gates = ["runbook reviewed", "owner matrix acknowledged", "triage rules loaded", "first-30-day review scheduled"]
    if strict:
        gates.append("executive launch support approval")
    return [{"id": f"PST-G{index}", "gate": gate, "blocking": True if strict or index <= 3 else False} for index, gate in enumerate(gates, start=1)]


def _review_cadence() -> list[dict[str, str]]:
    return [{"id": "PST-C1", "period": "day 1", "activity": "launch support review"}, {"id": "PST-C2", "period": "day 7", "activity": "ticket trend review"}, {"id": "PST-C3", "period": "day 30", "activity": "transition closeout"}]


def _source(unit: Any, spec: dict[str, Any]) -> dict[str, str]:
    return {"idea_id": _first(_field(unit, "id"), _nested(spec, "source", "idea_id"), "unknown"), "title": _first(_field(unit, "title"), _nested(spec, "project", "title"), "Untitled support transition"), "domain": _first(_field(unit, "domain"), _nested(spec, "source", "domain"), "")}


def _header(plan: dict[str, Any], label: str) -> list[str]:
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    return [f"# {_text(source.get('title'))} {label}", "", f"- Schema version: {_text(plan.get('schema_version'))}", f"- Kind: {_text(plan.get('kind'))}", ""]


def _extend(lines: list[str], title: str, items: list[dict[str, Any]], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    for item in items:
        lines.extend(renderer(item))
    lines.append("")


def _field(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None) if obj is not None else None


def _nested(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _list(data: dict[str, Any], section: str, key: str) -> list[str]:
    return _values(_nested(data, section, key))


def _values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in sorted(value.items()) if _compact(item)]
    if isinstance(value, list):
        result = []
        for item in value:
            compacted = _compact(item.get("name") or item.get("description") or item.get("risk")) if isinstance(item, dict) else _compact(item)
            if compacted:
                result.append(compacted)
        return result
    compacted = _compact(value)
    return [compacted] if compacted else []


def _dedupe(values: list[str]) -> list[str]:
    result, seen = [], set()
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _first(*values: Any) -> str:
    return next((_compact(value) for value in values if _compact(value)), "")


def _number(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _compact(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _text(value: Any) -> str:
    return "" if value is None else str(value)
