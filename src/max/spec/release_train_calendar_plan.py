"""Generate deterministic release train calendar plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-release-train-calendar-plan/v1"
KIND = "max.spec.release_train_calendar_plan"


def generate_release_train_calendar_plan(unit: Any, evaluation: Any | None = None, tact_spec_preview: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = tact_spec_preview if isinstance(tact_spec_preview, dict) else {}
    milestones = _milestones(unit, spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(unit, spec),
        "milestones": milestones,
        "freeze_windows": _freeze_windows(),
        "validation_checkpoints": _validation_checkpoints(unit, spec),
        "dependency_deadlines": _dependency_deadlines(spec),
        "owner_assignments": _owner_assignments(unit),
        "go_no_go_reviews": _go_no_go_reviews(evaluation),
    }


def render_release_train_calendar_plan_markdown(plan: dict[str, Any]) -> str:
    lines = _header(plan, "Release Train Calendar Plan")
    for title, key in (("Milestones", "milestones"), ("Freeze Windows", "freeze_windows"), ("Validation Checkpoints", "validation_checkpoints"), ("Dependency Deadlines", "dependency_deadlines"), ("Owner Assignments", "owner_assignments"), ("Go/No-Go Reviews", "go_no_go_reviews")):
        _extend(lines, title, plan.get(key) or [], lambda item: [f"- {item['id']}: {item.get('name') or item.get('checkpoint') or item.get('dependency') or item.get('role')} offset={item.get('offset')}"])
    return "\n".join(lines).rstrip() + "\n"


def _milestones(unit: Any, spec: dict[str, Any]) -> list[dict[str, str]]:
    names = ["scope lock", "build complete", "MVP validation", "release candidate", "launch"]
    return [{"id": f"RTC-M{index}", "name": name, "offset": f"T-{(len(names) - index) * 5}d" if name != "launch" else "T+0d", "owner": _first(_field(unit, "buyer"), "release owner")} for index, name in enumerate(names, start=1)]


def _freeze_windows() -> list[dict[str, str]]:
    return [{"id": "RTC-F1", "name": "code freeze", "offset": "T-5d to T+0d"}, {"id": "RTC-F2", "name": "data freeze", "offset": "T-2d to T+0d"}]


def _validation_checkpoints(unit: Any, spec: dict[str, Any]) -> list[dict[str, str]]:
    seeds = _values(_field(unit, "validation_plan")) + _list(spec, "execution", "mvp_scope") or ["MVP validation checkpoint"]
    return [{"id": f"RTC-V{index}", "checkpoint": item if "MVP" in item else f"MVP validation: {item}", "offset": f"T-{10 - index}d", "owner": "qa_owner"} for index, item in enumerate(_dedupe(seeds)[:4], start=1)]


def _dependency_deadlines(spec: dict[str, Any]) -> list[dict[str, str]]:
    deps = _list(spec, "execution", "dependencies") or ["customer approval", "support readiness"]
    return [{"id": f"RTC-D{index}", "dependency": dep, "offset": f"T-{8 - index}d", "owner": "dependency_owner"} for index, dep in enumerate(deps, start=1)]


def _owner_assignments(unit: Any) -> list[dict[str, str]]:
    roles = [("release owner", _first(_field(unit, "buyer"), "release sponsor")), ("validation owner", _first(_field(unit, "specific_user"), "qa owner")), ("support owner", "support lead")]
    return [{"id": f"RTC-O{index}", "role": role, "owner": owner, "offset": "T-15d"} for index, (role, owner) in enumerate(roles, start=1)]


def _go_no_go_reviews(evaluation: Any | None) -> list[dict[str, str]]:
    strict = (_number(_field(evaluation, "overall_score")) or 100) < 60
    return [{"id": "RTC-G1", "name": "pre-freeze go/no-go", "offset": "T-6d", "condition": "all blockers owned"}, {"id": "RTC-G2", "name": "launch go/no-go", "offset": "T-1d", "condition": "executive approval required" if strict else "release owner approval required"}]


def _source(unit: Any, spec: dict[str, Any]) -> dict[str, str]:
    return {"idea_id": _first(_field(unit, "id"), _nested(spec, "source", "idea_id"), "unknown"), "title": _first(_field(unit, "title"), _nested(spec, "project", "title"), "Untitled release train"), "domain": _first(_field(unit, "domain"), "")}


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
