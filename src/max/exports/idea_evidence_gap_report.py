"""Idea evidence gap export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.idea_evidence_gap_report.v1"
KIND = "max.idea_evidence_gap_report"
REQUIRED_ROLES = ("problem", "market", "solution")
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def generate_idea_evidence_gap_report(units: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for raw in units:
        roles = _roles(raw)
        missing = [role for role in REQUIRED_ROLES if role not in roles]
        severity = "high" if "problem" in missing else "medium" if missing else "low"
        rows.append({"unit_id": _text(raw.get("unit_id") or raw.get("id") or raw.get("idea_id")) or "unknown-unit", "present_roles": sorted(roles), "missing_roles": missing, "total_missing_roles": len(missing), "severity": severity})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["total_missing_roles"], row["unit_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"unit_count": len(rows), "gap_count": sum(1 for r in rows if r["total_missing_roles"]), "high_severity_count": sum(1 for r in rows if r["severity"] == "high")}, "rows": rows}


def _roles(raw: dict[str, Any]) -> set[str]:
    values = raw.get("evidence_roles") or raw.get("roles")
    if values is None:
        values = raw.get("evidence") or raw.get("evidence_signals") or []
    roles: set[str] = set()
    if isinstance(values, dict):
        iterable = values.values() if not any(k in REQUIRED_ROLES for k in values) else values.keys()
    else:
        iterable = values if isinstance(values, list | tuple | set) else [values]
    for item in iterable:
        if isinstance(item, dict):
            role = item.get("role") or item.get("evidence_role") or item.get("type")
        else:
            role = item
        text = _text(role).casefold()
        if text in REQUIRED_ROLES:
            roles.add(text)
    return roles


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
