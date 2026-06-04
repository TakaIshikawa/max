"""Buildable unit stack risk export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.buildable_unit_stack_risk_report.v1"
KIND = "max.buildable_unit_stack_risk_report"
UNSUPPORTED_RUNTIMES = {"python2", "python 2", "node10", "node 10", "node12", "node 12", "ruby2.6", "ruby 2.6"}
RISK_RANK = {"high": 0, "medium": 1, "low": 2}


def generate_buildable_unit_stack_risk_report(units: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for raw in units:
        stack = raw.get("stack") if isinstance(raw.get("stack"), dict) else {}
        runtime = _text(raw.get("runtime") or stack.get("runtime") or raw.get("language_runtime")).casefold()
        dependencies = raw.get("dependencies") or stack.get("dependencies") or raw.get("suggested_stack") or []
        unknown_dependency_count = sum(1 for dependency in _items(dependencies) if _is_unknown_dependency(dependency))
        deployment_target = _text(raw.get("deployment_target") or stack.get("deployment_target") or raw.get("deploy_target"))
        unsupported_runtime = runtime in UNSUPPORTED_RUNTIMES or runtime.startswith(("python 2.", "python2.", "node 10.", "node10.", "node 12.", "node12."))
        missing_deployment_target = deployment_target == ""
        risk = _risk(unsupported_runtime, unknown_dependency_count, missing_deployment_target)
        rows.append({"unit_id": _text(raw.get("unit_id") or raw.get("id") or raw.get("idea_id")) or "unknown-unit", "unsupported_runtime": unsupported_runtime, "unknown_dependency_count": unknown_dependency_count, "missing_deployment_target": missing_deployment_target, "risk": risk})
    rows.sort(key=lambda row: (RISK_RANK[row["risk"]], row["unit_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"unit_count": len(rows), "risky_unit_count": sum(1 for r in rows if r["risk"] != "low"), "unsupported_runtime_count": sum(1 for r in rows if r["unsupported_runtime"]), "missing_deployment_target_count": sum(1 for r in rows if r["missing_deployment_target"])}, "rows": rows}


def _risk(unsupported_runtime: bool, unknown_dependency_count: int, missing_deployment_target: bool) -> str:
    if unsupported_runtime or unknown_dependency_count >= 3:
        return "high"
    if missing_deployment_target or unknown_dependency_count > 0:
        return "medium"
    return "low"


def _items(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list | tuple | set):
        return list(value)
    return [value] if value else []


def _is_unknown_dependency(value: Any) -> bool:
    if isinstance(value, dict):
        text = _text(value.get("name") or value.get("package") or value.get("dependency"))
        status = _text(value.get("status") or value.get("state")).casefold()
        return text == "" or status in {"unknown", "unresolved", "unverified"}
    text = _text(value).casefold()
    return text in {"", "unknown", "tbd", "?"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
