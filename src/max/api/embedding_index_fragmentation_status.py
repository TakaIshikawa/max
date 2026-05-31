"""JSON API renderer for embedding index fragmentation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.embedding_index_fragmentation_status.v1"
KIND = "max.api.embedding_index_fragmentation_status"


def embedding_index_fragmentation_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "fragmented_indexes": [row for row in rows if row["severity"] != "ok"], "metadata": source_metadata(payload, index_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("indexes") if isinstance(payload.get("indexes"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    rows.sort(key=lambda row: (_rank(row["severity"]), -row["fragmentation_ratio"], row["index"]))
    return rows


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    total = max(0, int_or_zero(item.get("total_vectors", item.get("vector_count"))))
    stale = max(0, int_or_zero(item.get("stale_vectors", item.get("deleted_vectors"))))
    deleted = max(0, int_or_zero(item.get("deleted_vectors")))
    stale_or_deleted = min(total, max(stale, deleted)) if total else max(stale, deleted)
    ratio = round(stale_or_deleted / total, 4) if total else 0.0
    segments = max(0, int_or_zero(item.get("segment_count", item.get("segments"))))
    pending = max(0, int_or_zero(item.get("pending_compactions", item.get("pending_compaction_count"))))
    severity = "critical" if ratio >= 0.35 or pending >= 3 else "warning" if ratio >= 0.15 or segments >= 20 or pending else "ok"
    return {"index": _bucket(item.get("index") or item.get("name"), "unknown_index"), "total_vectors": total, "stale_vectors": stale_or_deleted, "segment_count": segments, "pending_compactions": pending, "fragmentation_ratio": ratio, "severity": severity, "recommended_action": "run_compaction" if severity == "critical" else "schedule_compaction" if severity == "warning" else "none"}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fragmented = sum(1 for row in rows if row["severity"] != "ok")
    return {"status": "fragmented" if fragmented else "ok", "index_count": len(rows), "fragmented_index_count": fragmented, "max_fragmentation_ratio": max((row["fragmentation_ratio"] for row in rows), default=0.0), "pending_compaction_count": sum(row["pending_compactions"] for row in rows)}


def _rank(value: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(value, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
