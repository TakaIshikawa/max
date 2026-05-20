"""Generate deterministic data access request fulfillment plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-data-access-request-fulfillment-plan/v1"
KIND = "max.spec.data_access_request_fulfillment_plan"


def generate_data_access_request_fulfillment_plan(unit: Any, evaluation: Any | None = None, tact_spec_preview: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = tact_spec_preview if isinstance(tact_spec_preview, dict) else {}
    risk = _risk_level(unit, evaluation, spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(unit, spec),
        "intake_fields": _intake_fields(unit),
        "verification_steps": _verification_steps(risk),
        "data_scope": _data_scope(unit, spec),
        "approval_workflow": _approval_workflow(risk),
        "fulfillment_steps": _fulfillment_steps(),
        "audit_evidence": _audit_evidence(risk),
        "denial_conditions": _denial_conditions(),
    }


def render_data_access_request_fulfillment_plan_markdown(plan: dict[str, Any]) -> str:
    lines = _header(plan, "Data Access Request Fulfillment Plan")
    for title, key in (("Intake Fields", "intake_fields"), ("Verification Steps", "verification_steps"), ("Data Scope", "data_scope"), ("Approval Workflow", "approval_workflow"), ("Fulfillment Steps", "fulfillment_steps"), ("Audit Evidence", "audit_evidence"), ("Denial Conditions", "denial_conditions")):
        _extend(lines, title, plan.get(key) or [], lambda item: [f"- {item['id']}: {item.get('field') or item.get('step') or item.get('scope') or item.get('condition') or item.get('evidence')}"])
    return "\n".join(lines).rstrip() + "\n"


def _intake_fields(unit: Any) -> list[dict[str, str]]:
    fields = ["requester identity", "request type", "data subject", "jurisdiction", _first(_field(unit, "domain"), "business domain")]
    return [{"id": f"DAR-I{index}", "field": field, "required": "true"} for index, field in enumerate(_dedupe(fields), start=1)]


def _verification_steps(risk: str) -> list[dict[str, str]]:
    steps = ["confirm requester identity", "validate authorization", "match request to data subject"]
    if risk == "high":
        steps.append("perform secondary privacy review")
    return [{"id": f"DAR-V{index}", "step": step, "owner": "privacy_ops"} for index, step in enumerate(steps, start=1)]


def _data_scope(unit: Any, spec: dict[str, Any]) -> list[dict[str, str]]:
    seeds = _values(_field(unit, "domain")) + _values(_field(unit, "category")) + _values(_nested(spec, "source", "domain")) + _list(spec, "data", "entities")
    seeds = seeds or ["customer profile data"]
    return [{"id": f"DAR-S{index}", "scope": item, "minimization_rule": "include only records required to fulfill the request"} for index, item in enumerate(_dedupe(seeds), start=1)]


def _approval_workflow(risk: str) -> list[dict[str, str]]:
    roles = ["privacy ops", "data owner"] + (["legal reviewer"] if risk == "high" else [])
    return [{"id": f"DAR-A{index}", "step": f"{role} approval", "owner": role, "required": "true"} for index, role in enumerate(roles, start=1)]


def _fulfillment_steps() -> list[dict[str, str]]:
    steps = ["locate scoped records", "export approved records", "redact excluded fields", "deliver through approved channel", "close request with evidence"]
    return [{"id": f"DAR-F{index}", "step": step} for index, step in enumerate(steps, start=1)]


def _audit_evidence(risk: str) -> list[dict[str, str]]:
    evidence = ["request intake record", "identity verification result", "approval log", "delivery confirmation"]
    if risk == "high":
        evidence.extend(["legal review note", "redaction proof"])
    return [{"id": f"DAR-E{index}", "evidence": item, "retention": "policy-defined retention period"} for index, item in enumerate(evidence, start=1)]


def _denial_conditions() -> list[dict[str, str]]:
    conditions = ["identity cannot be verified", "requester lacks authorization", "request conflicts with legal hold", "scope is unclear after clarification"]
    return [{"id": f"DAR-D{index}", "condition": item} for index, item in enumerate(conditions, start=1)]


def _risk_level(unit: Any, evaluation: Any | None, spec: dict[str, Any]) -> str:
    score = _number(_field(evaluation, "overall_score"))
    text = " ".join(_values(_field(unit, "domain_risks")) + _values(_field(evaluation, "weaknesses")) + _list(spec, "execution", "risks")).lower()
    return "high" if (score is not None and score < 60) or any(term in text for term in ("privacy", "security", "compliance", "legal")) else "standard"


def _source(unit: Any, spec: dict[str, Any]) -> dict[str, str]:
    return {"idea_id": _first(_field(unit, "id"), _nested(spec, "source", "idea_id"), "unknown"), "title": _first(_field(unit, "title"), _nested(spec, "project", "title"), "Untitled data access plan"), "domain": _first(_field(unit, "domain"), _nested(spec, "source", "domain"), "")}


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
    if isinstance(value, list):
        result = []
        for item in value:
            compacted = _compact(item.get("name") or item.get("entity") or item.get("description")) if isinstance(item, dict) else _compact(item)
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
