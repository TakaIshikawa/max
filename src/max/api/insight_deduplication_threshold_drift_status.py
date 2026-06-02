"""JSON API renderer for insight deduplication threshold drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.insight_deduplication_threshold_drift_status.v1"
KIND = "max.api.insight_deduplication_threshold_drift_status"


def insight_deduplication_threshold_drift_status_to_json(payload: Mapping[str, Any]) -> str:
    warning_delta = float_or_zero(payload.get("warning_delta")) or 0.05
    critical_delta = float_or_zero(payload.get("critical_delta")) or 0.15
    error_critical = float_or_zero(payload.get("critical_error_rate")) or 0.1
    rows = [_row(row, warning_delta, critical_delta, error_critical) for row in _items(payload)]
    rows.sort(key=lambda row: (_rank(row["status"]), -row["threshold_delta"], row["profile"]))
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": "critical" if critical else "warning" if warning else "ok", "summary": {"profile_count": len(rows), "critical_count": critical, "warning_count": warning}, "rows": rows, "metadata": source_metadata(payload, profile_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("thresholds")) or list_of_maps(payload.get("profiles")) or list_of_maps(payload.get("items"))


def _row(row: Mapping[str, Any], warning_delta: float, critical_delta: float, error_critical: float) -> dict[str, Any]:
    current = float_or_zero(row.get("current_threshold"))
    baseline = float_or_zero(row.get("baseline_threshold"))
    delta = round(abs(current - baseline), 4)
    merge = float_or_zero(row.get("merge_error_rate"))
    split = float_or_zero(row.get("split_error_rate"))
    status = "critical" if delta >= critical_delta or merge >= error_critical or split >= error_critical else "warning" if delta >= warning_delta else "ok"
    return {"profile": _bucket(row.get("profile") or row.get("insight_family"), "unknown_profile"), "current_threshold": current, "baseline_threshold": baseline, "threshold_delta": delta, "duplicate_rate": float_or_zero(row.get("duplicate_rate")), "merge_error_rate": merge, "split_error_rate": split, "status": status}


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
