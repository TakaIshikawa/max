"""JSON API renderer for source adapter pagination anomaly status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_pagination_anomaly_status.v1"
KIND = "max.api.source_adapter_pagination_anomaly_status"
STATUS_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def source_adapter_pagination_anomaly_status_to_json(payload: Mapping[str, Any], *, warning_threshold: int = 1, critical_threshold: int = 3) -> str:
    rows = [_row(item, index, warning_threshold, critical_threshold) for index, item in enumerate(list_of_maps(payload.get("runs") or payload.get("rows") or payload.get("items")), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["adapter"], row["run_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "critical" if any(row["status"] == "critical" for row in rows) else "warning" if any(row["status"] == "warning" for row in rows) else "healthy", "run_count": len(rows), "affected_run_count": sum(1 for row in rows if row["status"] != "healthy")}, "runs": rows, "metadata": source_metadata(payload, run_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, warning: int, critical: int) -> dict[str, Any]:
    duplicate = max(0, int_or_zero(item.get("duplicate_page_count")))
    skipped = max(0, int_or_zero(item.get("skipped_page_count")))
    repeated = max(0, int_or_zero(item.get("repeated_cursor_count")))
    score = duplicate + skipped + repeated
    status = "critical" if skipped >= critical or repeated >= critical or score >= critical else "warning" if score >= warning else "healthy"
    return {"adapter": _text(item.get("adapter") or item.get("adapter_id")) or "unknown", "run_id": _text(item.get("run_id") or item.get("id")) or f"run-{index}", "duplicate_page_count": duplicate, "skipped_page_count": skipped, "repeated_cursor_count": repeated, "anomaly_severity": status, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
