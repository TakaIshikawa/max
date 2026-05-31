"""JSON API renderer for embedding reindex throughput status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.embedding_reindex_throughput_status.v1"
KIND = "max.api.embedding_reindex_throughput_status"


def embedding_reindex_throughput_status_to_json(payload: Mapping[str, Any]) -> str:
    queued = int_or_zero(payload.get("queued_items", payload.get("queued")))
    processed = int_or_zero(payload.get("processed_items", payload.get("processed")))
    rate = round(max(0.0, float_or_zero(payload.get("processing_rate_per_minute", payload.get("rate_per_minute")))), 4)
    workers = [_worker(item, index) for index, item in enumerate(list_of_maps(payload.get("workers")), start=1)]
    stalled = [row for row in workers if row["stalled"]]
    if queued <= 0:
        status = "healthy"
    elif rate <= 0 or stalled:
        status = "critical"
    else:
        status = "healthy"
    eta = None if queued <= 0 or rate <= 0 else {"minutes": round(queued / rate, 2), "status": "available"}
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "queued_items": queued, "processed_items": processed, "processing_rate_per_minute": rate, "stalled_worker_count": len(stalled)}, "estimated_completion": eta or {"status": "unavailable"}, "workers": workers, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _worker(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {"worker_id": _text(item.get("worker_id") or item.get("id")) or f"worker-{index}", "processed_items": int_or_zero(item.get("processed_items", item.get("processed"))), "stalled": bool(item.get("stalled"))}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
