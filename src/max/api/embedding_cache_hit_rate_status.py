"""JSON API renderer for embedding cache hit rate status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.embedding_cache_hit_rate_status.v1"
KIND = "max.api.embedding_cache_hit_rate_status"
STATUS_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def embedding_cache_hit_rate_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_min_hit_rate"), 0.75)
    critical = _float(payload.get("critical_min_hit_rate"), 0.5)
    rows = [_row(item, index, warning, critical) for index, item in enumerate(list_of_maps(payload.get("namespaces") or payload.get("rows") or payload.get("caches")), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["hit_rate"], -row["request_count"], row["namespace"]))
    total_hits = sum(row["hits"] for row in rows)
    total_misses = sum(row["misses"] for row in rows)
    total = total_hits + total_misses
    hit_rate = round(total_hits / total, 4) if total else 0.0
    low = [row for row in rows if row["status"] != "healthy"]
    status = "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if low else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "namespace_count": len(rows), "request_count": total, "hits": total_hits, "misses": total_misses, "hit_rate": hit_rate}, "namespaces": rows, "low_hit_rate_namespaces": low, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    hits = max(0, int_or_zero(item.get("hits", item.get("hit_count"))))
    misses = max(0, int_or_zero(item.get("misses", item.get("miss_count"))))
    total = hits + misses
    rate = round(hits / total, 4) if total else 0.0
    status = "healthy" if total == 0 or rate >= warning else ("critical" if rate < critical else "warning")
    return {"namespace": str(item.get("namespace") or item.get("model") or item.get("embedding_model") or f"namespace-{index}"), "embedding_model": str(item.get("embedding_model") or item.get("model") or "unknown_model"), "hits": hits, "misses": misses, "request_count": total, "hit_rate": rate, "status": status}


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default
