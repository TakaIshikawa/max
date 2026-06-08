"""JSON API renderer for source adapter payload size status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_payload_size_status.v1"
KIND = "max.api.source_adapter_payload_size_status"
STATUS_RANK = {"critical": 0, "warning": 1, "healthy": 2, "idle": 3}


def source_adapter_payload_size_status_to_json(payload: Mapping[str, Any], *, warning_bytes: int = 512_000, critical_bytes: int = 1_048_576) -> str:
    rows = [_row(item, warning_bytes, critical_bytes) for item in list_of_maps(payload.get("adapters") or payload.get("rows") or payload.get("items"))]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["adapter"], row["source"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "critical" if any(row["status"] == "critical" for row in rows) else "warning" if any(row["status"] == "warning" for row in rows) else "healthy" if rows else "idle", "adapter_count": len(rows), "oversized_count": sum(1 for row in rows if row["status"] in {"warning", "critical"})}, "adapters": rows, "metadata": source_metadata(payload, adapter_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], warning: int, critical: int) -> dict[str, Any]:
    payload_bytes = max(0, int_or_zero(item.get("payload_bytes", item.get("bytes"))))
    records = max(0, int_or_zero(item.get("record_count", item.get("records"))))
    status = "idle" if records == 0 and payload_bytes == 0 else "critical" if payload_bytes >= critical else "warning" if payload_bytes >= warning else "healthy"
    return {"adapter": _text(item.get("adapter") or item.get("adapter_id")) or "unknown", "source": _text(item.get("source") or item.get("source_id")) or "unknown", "payload_bytes": payload_bytes, "payload_kib": round(payload_bytes / 1024, 2), "record_count": records, "bytes_per_record": round(payload_bytes / records, 2) if records else 0.0, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
