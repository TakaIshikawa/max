"""JSON API renderer for buildable unit dependency freshness status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.buildable_unit_dependency_freshness_status.v1"
KIND = "max.api.buildable_unit_dependency_freshness_status"


def buildable_unit_dependency_freshness_status_to_json(payload: Mapping[str, Any]) -> str:
    stale_days = max(0, int_or_zero(payload.get("stale_days"))) or 30
    critical_days = max(0, int_or_zero(payload.get("critical_days"))) or 90
    stale_count_threshold = max(1, int_or_zero(payload.get("stale_dependency_count_threshold")) or 3)
    units = [_unit(row, stale_days, critical_days, stale_count_threshold) for row in _items(payload)]
    units.sort(key=lambda row: (_rank(row["status"]), row["unit_id"]))
    summary = _summary(units)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "units": units, "stack_hot_spots": _stacks(units), "metadata": source_metadata(payload, unit_count=len(units))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("units")) or list_of_maps(payload.get("items")) or list_of_maps(payload.get("rows"))


def _deps(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [{"name": name, **mapping(details)} for name, details in value.items()]
    return list_of_maps(value)


def _unit(row: Mapping[str, Any], stale_days: int, critical_days: int, stale_count_threshold: int) -> dict[str, Any]:
    deps = [_dependency(dep, stale_days, critical_days) for dep in _deps(row.get("dependencies"))]
    stale_count = sum(1 for dep in deps if dep["status"] != "ok")
    critical = any(dep["status"] == "critical" for dep in deps) or stale_count >= stale_count_threshold
    status = "critical" if critical else "warning" if stale_count else "ok"
    return {"unit_id": _bucket(row.get("unit_id") or row.get("id"), "unknown_unit"), "stack": _bucket(row.get("stack"), "unknown_stack"), "stale_dependency_count": stale_count, "dependencies": deps, "status": status}


def _dependency(dep: Mapping[str, Any], stale_days: int, critical_days: int) -> dict[str, Any]:
    days = max(0, int_or_zero(dep.get("days_behind")))
    status = "critical" if days >= critical_days else "warning" if days >= stale_days else "ok"
    return {"name": _bucket(dep.get("name"), "unknown_dependency"), "current_version": dep.get("current_version"), "latest_version": dep.get("latest_version"), "released_at": dep.get("released_at"), "days_behind": days, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    stale_units = sum(1 for row in rows if row["status"] != "ok")
    stale_deps = sum(row["stale_dependency_count"] for row in rows)
    return {"status": "critical" if critical else "warning" if stale_units else "ok", "unit_count": len(rows), "stale_unit_count": stale_units, "stale_dependency_count": stale_deps, "critical_count": critical}


def _stacks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter(row["stack"] for row in rows if row["status"] != "ok")
    return [{"stack": stack, "stale_unit_count": count} for stack, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
