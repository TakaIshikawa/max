"""JSON API renderer for buildable unit evaluation readiness status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, source_metadata

SCHEMA_VERSION = "max.api.buildable_unit_evaluation_readiness_status.v1"
KIND = "max.api.buildable_unit_evaluation_readiness_status"
REQUIRED_FIELDS = ("problem", "solution", "target_user", "stack", "evidence_ids", "profile_id")


def buildable_unit_evaluation_readiness_status_to_json(
    payload: Mapping[str, Any],
    *,
    warning_blocked_ratio: float | None = None,
    critical_blocked_ratio: float | None = None,
) -> str:
    warn = _ratio(warning_blocked_ratio if warning_blocked_ratio is not None else payload.get("warning_blocked_ratio"), 0.25)
    critical = _ratio(critical_blocked_ratio if critical_blocked_ratio is not None else payload.get("critical_blocked_ratio"), 0.5)
    rows = [_row(item) for item in _items(payload)]
    rows.sort(key=lambda row: (not row["blocked"], row["unit_id"]))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows, warn, critical), "rows": rows, "metadata": source_metadata(payload, unit_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    source = payload.get("buildable_units") if isinstance(payload.get("buildable_units"), list) else payload.get("units")
    return [item for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if not _present(item, field)]
    return {"unit_id": str(item.get("unit_id") or item.get("id") or "unknown_unit"), "ready": not missing, "blocked": bool(missing), "missing_fields": missing}


def _present(item: Mapping[str, Any], field: str) -> bool:
    if field == "evidence_ids":
        return bool(as_list(item.get("evidence_ids") or item.get("evidence")))
    if field == "stack":
        return bool(as_list(item.get("stack") or item.get("stack_tags")))
    return item.get(field) not in (None, "", [])


def _summary(rows: list[dict[str, Any]], warn: float, critical: float) -> dict[str, Any]:
    total = len(rows)
    blocked = sum(1 for row in rows if row["blocked"])
    ratio = round(blocked / total, 4) if total else 0.0
    severity = "critical" if ratio >= critical and blocked else "warn" if ratio >= warn and blocked else "healthy"
    missing_counts = {field: sum(1 for row in rows if field in row["missing_fields"]) for field in REQUIRED_FIELDS}
    return {"severity": severity, "unit_count": total, "ready_count": total - blocked, "blocked_count": blocked, "blocked_ratio": ratio, "missing_field_counts": missing_counts, "warning_blocked_ratio": warn, "critical_blocked_ratio": critical}


def _ratio(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if number > 1:
        number /= 100
    return round(min(max(number, 0.0), 1.0), 4)
