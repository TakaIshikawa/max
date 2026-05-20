"""Generate deterministic integration health check plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-integration-health-check-plan/v1"
KIND = "max.spec.integration_health_check_plan"


def generate_integration_health_check_plan(unit: Any, evaluation: Any | None = None, tact_spec_preview: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = tact_spec_preview if isinstance(tact_spec_preview, dict) else {}
    dependencies = _dependencies(unit, spec)
    checks = _health_checks(dependencies)
    failures = _failure_modes(dependencies, evaluation, spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(unit, spec),
        "dependency_inventory": dependencies,
        "health_checks": checks,
        "failure_modes": failures,
        "owner_routes": _owner_routes(dependencies),
        "recovery_checks": _recovery_checks(dependencies),
        "launch_gate": _launch_gate(checks, failures, evaluation),
    }


def render_integration_health_check_plan_markdown(plan: dict[str, Any]) -> str:
    lines = _header(plan, "Integration Health Check Plan")
    _extend(lines, "Dependency Inventory", plan.get("dependency_inventory") or [], lambda item: [f"- {item['id']}: {item['name']} direction={item['direction']} owner={item['owner']}"])
    _extend(lines, "Health Checks", plan.get("health_checks") or [], lambda item: [f"- {item['id']}: {item['probe']} expected={item['expected_result']}"])
    _extend(lines, "Failure Modes", plan.get("failure_modes") or [], lambda item: [f"- {item['id']}: {item['symptom']} route={item['route_to']}"])
    _extend(lines, "Launch Gate", [plan.get("launch_gate") or {}], lambda item: [f"- Criteria: {item.get('criteria')}"])
    return "\n".join(lines).rstrip() + "\n"


def _dependencies(unit: Any, spec: dict[str, Any]) -> list[dict[str, str]]:
    values = _list(_nested(spec, "solution", "suggested_stack")) + _list(_nested(spec, "execution", "dependencies")) + _values(_field(unit, "suggested_stack"))
    if not values:
        values = ["primary customer system"]
    return [{"id": f"IHC-D{index}", "name": value, "direction": "upstream" if index % 2 else "downstream", "owner": "integration_owner", "source": "tact_spec" if spec else "fallback"} for index, value in enumerate(_dedupe(values)[:6], start=1)]


def _health_checks(dependencies: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": f"IHC-H{index}", "dependency_id": item["id"], "probe": f"Verify {item['name']} connectivity and contract response", "expected_result": "healthy response within agreed timeout", "cadence": "pre-launch and hourly for first day"} for index, item in enumerate(dependencies, start=1)]


def _failure_modes(dependencies: list[dict[str, str]], evaluation: Any | None, spec: dict[str, Any]) -> list[dict[str, str]]:
    risks = _values(_field(evaluation, "weaknesses")) + _values(_nested(spec, "execution", "risks"))
    rows = [{"id": f"IHC-F{index}", "dependency_id": item["id"], "symptom": f"{item['name']} unavailable or returning invalid data", "route_to": item["owner"], "recovery_hint": "pause launch and run recovery check"} for index, item in enumerate(dependencies, start=1)]
    for risk in risks[:2]:
        rows.append({"id": f"IHC-F{len(rows) + 1}", "dependency_id": "cross-cutting", "symptom": risk, "route_to": "launch_owner", "recovery_hint": "confirm mitigation before go/no-go"})
    return rows


def _owner_routes(dependencies: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": f"IHC-O{index}", "dependency_id": item["id"], "owner": item["owner"], "escalation": "launch_manager"} for index, item in enumerate(dependencies, start=1)]


def _recovery_checks(dependencies: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": f"IHC-R{index}", "dependency_id": item["id"], "check": f"Replay last successful {item['name']} transaction", "pass_condition": "transaction completes and monitoring clears"} for index, item in enumerate(dependencies, start=1)]


def _launch_gate(checks: list[dict[str, str]], failures: list[dict[str, str]], evaluation: Any | None) -> dict[str, Any]:
    score = _number(_field(evaluation, "overall_score"))
    return {"criteria": "all health checks pass with no open critical failure modes", "required_passes": len(checks), "failure_mode_count": len(failures), "strict": bool(score is not None and score < 60)}


def _source(unit: Any, spec: dict[str, Any]) -> dict[str, str]:
    return {"idea_id": _first(_field(unit, "id"), _nested(spec, "source", "idea_id"), "unknown"), "title": _first(_field(unit, "title"), _nested(spec, "project", "title"), "Untitled integration"), "domain": _first(_field(unit, "domain"), _nested(spec, "source", "domain"), "")}


def _header(plan: dict[str, Any], label: str) -> list[str]:
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    return [f"# {_text(source.get('title')) or 'Integration'} {label}", "", f"- Schema version: {_text(plan.get('schema_version'))}", f"- Kind: {_text(plan.get('kind'))}", f"- Source idea ID: {_text(source.get('idea_id'))}", ""]


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


def _list(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in sorted(value.items()) if _compact(item)]
    return _values(value)


def _values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in sorted(value.items()) if _compact(item)]
    if isinstance(value, list):
        result = []
        for item in value:
            compacted = _compact(item.get("name") or item.get("dependency") or item.get("description")) if isinstance(item, dict) else _compact(item)
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
