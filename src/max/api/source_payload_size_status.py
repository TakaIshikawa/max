"""JSON API renderer for source payload size status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.source_payload_size_status.v1"
KIND = "max.api.source_payload_size_status"


def source_payload_size_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "oversized_sources": [row for row in rows if row["oversized"]], "metadata": source_metadata(payload, source_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("sources") if isinstance(payload.get("sources"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["oversized"], -row["payload_bytes"], row["source"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    payload_bytes = max(0, int_or_zero(item.get("payload_bytes")))
    max_payload = max(0, int_or_zero(item.get("max_payload_bytes")))
    records = max(0, int_or_zero(item.get("record_count")))
    ratio = float_or_zero(payload_bytes) / max_payload if max_payload else (1.0 if payload_bytes else 0.0)
    oversized = bool(max_payload and payload_bytes > max_payload)
    return {"source": _bucket(item.get("source"), "unknown_source"), "adapter": _bucket(item.get("adapter"), "unknown_adapter"), "window": _text(item.get("window")) or "current", "payload_bytes": payload_bytes, "max_payload_bytes": max_payload, "record_count": records, "payload_kib": round(payload_bytes / 1024, 2), "bytes_per_record": round(payload_bytes / records, 2) if records else 0.0, "oversized": oversized, "severity": "critical" if ratio >= 1.5 else "warning" if oversized else "ok"}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    oversized_count = sum(1 for row in rows if row["oversized"])
    return {"status": "oversized" if oversized_count else "ok", "source_count": len(rows), "oversized_count": oversized_count, "total_payload_bytes": sum(row["payload_bytes"] for row in rows)}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
