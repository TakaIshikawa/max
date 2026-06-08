"""JSON API summary renderer for source adapter payload sizes."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_payload_size_summary.v1"
KIND = "max.api.source_adapter_payload_size_summary"


def source_adapter_payload_size_summary_to_json(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> str:
    rows = _items(payload)
    total_bytes = sum(max(0, int_or_zero(item.get("payload_bytes", item.get("bytes")))) for item in rows)
    total_records = sum(max(0, int_or_zero(item.get("record_count", item.get("records")))) for item in rows)
    adapters = sorted({_text(item.get("adapter")) or "unknown" for item in rows})
    metadata = source_metadata(payload if isinstance(payload, Mapping) else {}, adapter_count=len(adapters))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "ok", "adapter_count": len(adapters), "payload_count": len(rows), "total_bytes": total_bytes, "total_records": total_records, "avg_bytes": round(total_bytes / len(rows), 2) if rows else 0.0, "bytes_per_record": round(total_bytes / total_records, 2) if total_records else 0.0}, "adapters": adapters, "metadata": metadata}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return list_of_maps(payload.get("payloads") or payload.get("adapters") or payload.get("rows") or payload.get("items"))
    return [item for item in payload if isinstance(item, Mapping)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
