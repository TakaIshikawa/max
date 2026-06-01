"""JSON API renderer for buildable unit stack policy status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.buildable_unit_stack_policy_status.v1"
KIND = "max.api.buildable_unit_stack_policy_status"


def buildable_unit_stack_policy_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_unit(row, i, payload) for i, row in enumerate(list_of_maps(payload.get("units") or payload.get("buildable_units") or payload.get("rows")), start=1)]
    violating = [row for row in rows if row["status"] != "healthy"]
    blocked_dependency_count = sum(len(row["blocked_dependencies"]) for row in rows)
    status = "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if violating else "healthy")
    output = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"unit_count": len(rows), "violating_unit_count": len(violating), "blocked_dependency_count": blocked_dependency_count, "status": status},
        "units": rows,
        "violating_units": sorted(violating, key=lambda row: (0 if row["status"] == "critical" else 1, row["unit"].casefold())),
        "violation_counts": dict(Counter(reason for row in rows for reason in row["violations"])),
        "metadata": source_metadata(payload),
    }
    return json.dumps(output, indent=2, sort_keys=True)


def _unit(item: Mapping[str, Any], index: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {value.casefold() for value in strings(item.get("allowed_stacks") or payload.get("allowed_stacks"))}
    blocked = {value.casefold() for value in strings(item.get("blocked_dependencies") or payload.get("blocked_dependencies"))}
    required_runtime = _text(item.get("required_runtime") or payload.get("required_runtime"))
    stack = strings(item.get("stack") or item.get("stacks") or item.get("dependencies"))
    runtime = _text(item.get("runtime"))
    violations: list[str] = []
    disallowed = sorted([entry for entry in stack if allowed and entry.casefold() not in allowed], key=str.casefold)
    blocked_hits = sorted([entry for entry in stack if entry.casefold() in blocked], key=str.casefold)
    if disallowed:
        violations.append("disallowed_stack")
    if blocked_hits:
        violations.append("blocked_dependency")
    if required_runtime and runtime and runtime.casefold() != required_runtime.casefold():
        violations.append("runtime_mismatch")
    status = "critical" if blocked_hits else ("warning" if violations else "healthy")
    return {"unit": _text(item.get("unit") or item.get("name") or item.get("id")) or f"unit-{index}", "stack": stack, "runtime": runtime or "unspecified", "allowed_stacks": sorted(allowed), "required_runtime": required_runtime, "disallowed_stack_items": disallowed, "blocked_dependencies": blocked_hits, "violations": violations, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
