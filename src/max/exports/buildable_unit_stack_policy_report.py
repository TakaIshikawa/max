"""Buildable unit stack policy export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.buildable_unit_stack_policy_report.v1"
KIND = "max.buildable_unit_stack_policy_report"


def generate_buildable_unit_stack_policy_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        profile = _text(raw.get("profile") or raw.get("domain_profile")) or "default"
        unit_id = _text(raw.get("buildable_unit_id") or raw.get("unit_id") or raw.get("id")) or "unknown-unit"
        group = groups.setdefault((profile, unit_id), {"technology": set(), "allowed": 0, "discouraged": 0, "disallowed": 0, "violated": set()})
        checks = _items(raw.get("checks") or raw.get("policy_checks") or raw.get("stack_policies")) or [raw]
        for check in checks:
            decision = _decision(check)
            technology = _text(check.get("technology") or check.get("tech") or check.get("runtime")) if isinstance(check, dict) else _text(raw.get("technology"))
            policy = _text(check.get("policy") or check.get("policy_id") or check.get("name")) if isinstance(check, dict) else ""
            if technology:
                group["technology"].add(technology)
            if decision == "disallowed":
                group["disallowed"] += 1
                group["violated"].add(policy or technology or "disallowed_policy")
            elif decision == "discouraged":
                group["discouraged"] += 1
            else:
                group["allowed"] += 1

    rows = []
    for (profile, unit_id), group in groups.items():
        status = "violation" if group["disallowed"] else ("warning" if group["discouraged"] else "ok")
        rows.append({"profile": profile, "buildable_unit_id": unit_id, "technologies": sorted(group["technology"], key=str.lower), "allowed_count": group["allowed"], "discouraged_count": group["discouraged"], "disallowed_count": group["disallowed"], "violated_policies": sorted(group["violated"], key=str.lower), "status": status})
    rows.sort(key=lambda row: (row["profile"].lower(), row["buildable_unit_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "violation_count": sum(1 for row in rows if row["status"] == "violation"), "warning_count": sum(1 for row in rows if row["status"] == "warning")}, "rows": rows}


def _items(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list | tuple | set):
        return list(value)
    return []


def _decision(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("decision") or value.get("status") or value.get("result")
    text = _text(value).lower()
    if text in {"disallowed", "deny", "denied", "blocked", "violation"}:
        return "disallowed"
    if text in {"discouraged", "warn", "warning", "caution"}:
        return "discouraged"
    return "allowed"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
