"""JSON API renderer for buildable unit stack compliance status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.buildable_unit_stack_compliance_status.v1"
KIND = "max.api.buildable_unit_stack_compliance_status"
DEFAULT_ALLOWED_RUNTIMES = {"python", "node", "go"}
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def buildable_unit_stack_compliance_status_to_json(records: Any, *, allowed_runtimes: set[str] | list[str] | tuple[str, ...] | None = None) -> str:
    payload = mapping(records)
    source = payload.get("units") or payload.get("records") or payload.get("items") or (records if isinstance(records, list) else [])
    allowed = {str(value).casefold() for value in (allowed_runtimes or DEFAULT_ALLOWED_RUNTIMES)}
    rows = [_row(item, index, allowed) for index, item in enumerate(list_of_maps(source), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["violation_count"], row["unit_id"]))
    status = "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if any(row["status"] == "warning" for row in rows) else "ok")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": status, "summary": {"unit_count": len(rows), "violating_unit_count": sum(1 for row in rows if row["violations"]), "status": status}, "units": rows, "metadata": source_metadata(payload, unit_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, allowed: set[str]) -> dict[str, Any]:
    runtime = _text(item.get("runtime") or item.get("language"))
    deployment_target = _text(item.get("deployment_target") or item.get("target"))
    violations: list[str] = []
    if not runtime:
        violations.append("missing_runtime")
    elif runtime.casefold() not in allowed:
        violations.append("unsupported_runtime")
    if not deployment_target:
        violations.append("missing_deployment_target")
    status = "critical" if "missing_runtime" in violations or "missing_deployment_target" in violations else ("warning" if violations else "ok")
    return {"unit_id": _text(item.get("unit_id") or item.get("id")) or f"unit-{index}", "runtime": runtime or None, "deployment_target": deployment_target or None, "violations": violations, "violation_count": len(violations), "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
