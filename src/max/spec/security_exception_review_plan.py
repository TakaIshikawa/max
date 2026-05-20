"""Generate deterministic security exception review plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-security-exception-review-plan/v1"
KIND = "max.spec.security_exception_review_plan"


def generate_security_exception_review_plan(unit: Any, evaluation: Any | None = None, tact_spec_preview: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = tact_spec_preview if isinstance(tact_spec_preview, dict) else {}
    controls = _affected_controls(unit, evaluation, spec)
    severity = "high" if len(controls) > 1 or (_number(_field(evaluation, "overall_score")) or 100) < 60 else "medium"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(unit, spec),
        "exception_scope": _exception_scope(unit, spec, severity),
        "affected_controls": controls,
        "compensating_controls": _compensating_controls(controls),
        "evidence_requirements": _evidence_requirements(controls),
        "approval_roles": _approval_roles(severity),
        "expiry_criteria": _expiry_criteria(severity),
        "renewal_triggers": _renewal_triggers(controls),
    }


def render_security_exception_review_plan_markdown(plan: dict[str, Any]) -> str:
    lines = _header(plan, "Security Exception Review Plan")
    _extend(lines, "Exception Scope", plan.get("exception_scope") or [], lambda item: [f"- {item['id']}: {item['scope']} severity={item['severity']}"])
    _extend(lines, "Affected Controls", plan.get("affected_controls") or [], lambda item: [f"- {item['id']}: {item['control']} severity={item['severity']}"])
    _extend(lines, "Compensating Controls", plan.get("compensating_controls") or [], lambda item: [f"- {item['id']}: {item['control']}"])
    _extend(lines, "Approval Roles", plan.get("approval_roles") or [], lambda item: [f"- {item['id']}: {item['role']} required={item['required']}"])
    return "\n".join(lines).rstrip() + "\n"


def _exception_scope(unit: Any, spec: dict[str, Any], severity: str) -> list[dict[str, str]]:
    scope = _values(_field(unit, "solution")) + _list(spec, "execution", "mvp_scope") or ["security exception under review"]
    return [{"id": f"SER-S{index}", "scope": item, "severity": severity, "boundary": "customer-facing launch scope"} for index, item in enumerate(_dedupe(scope)[:3], start=1)]


def _affected_controls(unit: Any, evaluation: Any | None, spec: dict[str, Any]) -> list[dict[str, str]]:
    seeds = _values(_field(unit, "domain_risks")) + _values(_field(evaluation, "weaknesses")) + _list(spec, "security", "controls")
    if not seeds:
        seeds = ["access review"]
    rows = []
    for index, item in enumerate(_dedupe(seeds)[:5], start=1):
        text = item.lower()
        severity = "high" if any(term in text for term in ("privacy", "security", "access", "encryption", "compliance")) else "medium"
        rows.append({"id": f"SER-C{index}", "control": item, "severity": severity, "owner": "security_owner"})
    return rows


def _compensating_controls(controls: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": f"SER-M{index}", "control": f"Compensating review for {item['control']}", "owner": item["owner"], "evidence": "control validation artifact"} for index, item in enumerate(controls, start=1)]


def _evidence_requirements(controls: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": f"SER-E{index}", "control_id": item["id"], "evidence": f"Exception rationale and test evidence for {item['control']}"} for index, item in enumerate(controls, start=1)]


def _approval_roles(severity: str) -> list[dict[str, Any]]:
    roles = ["security owner", "product owner"] + (["risk committee"] if severity == "high" else [])
    return [{"id": f"SER-A{index}", "role": role, "required": True} for index, role in enumerate(roles, start=1)]


def _expiry_criteria(severity: str) -> list[dict[str, str]]:
    return [{"id": "SER-X1", "criteria": "exception expires after 30 days" if severity == "high" else "exception expires after 90 days"}]


def _renewal_triggers(controls: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": f"SER-R{index}", "trigger": f"{item['control']} remains unresolved at expiry"} for index, item in enumerate(controls, start=1)]


def _source(unit: Any, spec: dict[str, Any]) -> dict[str, str]:
    return {"idea_id": _first(_field(unit, "id"), _nested(spec, "source", "idea_id"), "unknown"), "title": _first(_field(unit, "title"), _nested(spec, "project", "title"), "Untitled security exception"), "domain": _first(_field(unit, "domain"), "")}


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
            compacted = _compact(item.get("name") or item.get("control") or item.get("description")) if isinstance(item, dict) else _compact(item)
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
