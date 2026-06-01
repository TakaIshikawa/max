"""JSON API renderer for fetch allocation drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.fetch_allocation_drift_status.v1"
KIND = "max.api.fetch_allocation_drift_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def fetch_allocation_drift_status_to_json(payload: Mapping[str, Any]) -> str:
    entries = [_entry(item, index) for index, item in enumerate(list_of_maps(payload.get("sources") or payload.get("allocations") or payload.get("rows")), start=1)]
    entries.sort(key=lambda row: (RANK[row["severity"]], row["source"]))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "critical" if any(row["severity"] == "critical" for row in entries) else ("warning" if any(row["severity"] == "warning" for row in entries) else "healthy"), "source_count": len(entries), "drifting_source_count": sum(1 for row in entries if row["severity"] != "healthy")}, "entries": entries, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _entry(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    target = float_or_zero(item.get("target_allocation", item.get("targetAllocation")))
    actual = float_or_zero(item.get("actual_allocation", item.get("actualAllocation")))
    drift = float_or_zero(item.get("delta", item.get("drift", actual - target)))
    threshold = float_or_zero(item.get("threshold"))
    severity = str(item.get("severity") or _severity(drift, threshold))
    return {"source": str(item.get("source") or item.get("source_id") or f"source-{index}"), "targetAllocation": round(target, 4), "actualAllocation": round(actual, 4), "drift": round(drift, 4), "threshold": round(threshold, 4), "severity": severity}


def _severity(drift: float, threshold: float) -> str:
    if threshold and abs(drift) >= threshold * 2:
        return "critical"
    if threshold and abs(drift) > threshold:
        return "warning"
    return "healthy"
