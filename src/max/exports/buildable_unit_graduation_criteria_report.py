"""Buildable unit graduation criteria export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.buildable_unit_graduation_criteria_report.v1"
KIND = "max.buildable_unit_graduation_criteria_report"


def generate_buildable_unit_graduation_criteria_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        profile = _text(raw.get("profile") or raw.get("domain_profile")) or "default"
        unit_id = _text(raw.get("buildable_unit_id") or raw.get("unit_id") or raw.get("id")) or "unknown-unit"
        group = groups.setdefault((profile, unit_id), {"passed": 0, "failed": 0, "missing": set()})
        criteria = raw.get("criteria") or raw.get("graduation_criteria") or raw.get("checks")
        items = _items(criteria) or [raw]
        for item in items:
            passed = _passed(item)
            required = _required(item)
            name = _criterion_name(item)
            if passed:
                group["passed"] += 1
            else:
                group["failed"] += 1
                if required:
                    group["missing"].add(name or "required_criterion")

    rows = []
    for (profile, unit_id), group in groups.items():
        total = group["passed"] + group["failed"]
        pass_rate = round(group["passed"] / total, 4) if total else 0.0
        missing = sorted(group["missing"], key=str.lower)
        rows.append(
            {
                "profile": profile,
                "buildable_unit_id": unit_id,
                "passed_count": group["passed"],
                "failed_count": group["failed"],
                "missing_required_criteria": missing,
                "pass_rate": pass_rate,
                "status": "blocked" if missing else "ready",
            }
        )
    rows.sort(key=lambda row: (row["profile"].lower(), row["buildable_unit_id"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "row_count": len(rows),
            "ready_count": sum(1 for row in rows if row["status"] == "ready"),
            "blocked_count": sum(1 for row in rows if row["status"] == "blocked"),
        },
        "rows": rows,
    }


def _items(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list | tuple | set):
        return list(value)
    return []


def _passed(value: Any) -> bool:
    if isinstance(value, dict):
        if "passed" in value:
            return _bool(value.get("passed"))
        status = _text(value.get("status") or value.get("result") or value.get("state")).lower()
        return status in {"pass", "passed", "ok", "ready", "met", "complete"}
    return _bool(value)


def _required(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    if "required" in value:
        return _bool(value.get("required"))
    return _text(value.get("severity") or value.get("priority")).lower() in {"required", "must", "blocker", "critical"}


def _criterion_name(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("criterion") or value.get("name") or value.get("id") or value.get("key"))
    return _text(value)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "pass", "passed", "ok", "ready", "met", "complete"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
