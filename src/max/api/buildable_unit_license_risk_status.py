"""JSON API renderer for buildable unit license risk status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.buildable_unit_license_risk_status.v1"
KIND = "max.api.buildable_unit_license_risk_status"
STATUS_RANK = {"blocked": 0, "warning": 1, "allowed": 2}


def buildable_unit_license_risk_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_unit(item, index) for index, item in enumerate(list_of_maps(payload.get("units") or payload.get("rows") or payload.get("items")), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["risk_level"]], row["unit_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "blocked" if any(row["risk_level"] == "blocked" for row in rows) else "warning" if any(row["risk_level"] == "warning" for row in rows) else "allowed", "unit_count": len(rows), "blocked_dependency_count": sum(row["blocked_dependency_count"] for row in rows)}, "units": rows, "metadata": source_metadata(payload, unit_count=len(rows))}, indent=2, sort_keys=True)


def _unit(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    dependencies = [_dependency(dep) for dep in list_of_maps(item.get("dependencies"))]
    blocked = sum(1 for dep in dependencies if dep["policy_decision"] in {"blocked", "unknown"})
    warning = any(dep["policy_decision"] == "review" for dep in dependencies)
    risk = "blocked" if blocked else "warning" if warning else "allowed"
    return {"unit_id": _text(item.get("unit_id") or item.get("buildable_unit_id") or item.get("id")) or f"unit-{index}", "dependencies": sorted(dependencies, key=lambda dep: (STATUS_RANK.get(dep["risk_level"], 9), dep["dependency"])), "blocked_dependency_count": blocked, "risk_level": risk, "status": risk}


def _dependency(item: Mapping[str, Any]) -> dict[str, Any]:
    decision = _text(item.get("policy_decision") or item.get("decision")).lower() or _decision_for_license(item.get("license"))
    if decision not in {"allowed", "review", "blocked", "unknown"}:
        decision = "unknown"
    risk = "blocked" if decision in {"blocked", "unknown"} else "warning" if decision == "review" else "allowed"
    return {"dependency": _text(item.get("dependency") or item.get("name")) or "unknown", "license": _text(item.get("license")) or "unknown", "policy_decision": decision, "risk_level": risk}


def _decision_for_license(value: Any) -> str:
    license_name = _text(value).lower()
    if not license_name or license_name == "unknown":
        return "unknown"
    if "gpl" in license_name or "agpl" in license_name:
        return "blocked"
    if "mpl" in license_name or "lgpl" in license_name:
        return "review"
    return "allowed"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
