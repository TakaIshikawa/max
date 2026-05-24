"""JSON API renderer for embedding index health."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.embedding_index_health.v1"
KIND = "max.api.embedding_index_health"
STATUS_RANK = {"dimension_mismatch": 0, "degraded": 1, "stale": 2, "rebuilding": 3, "healthy": 4}


def embedding_index_health_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    indexes = _indexes(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(indexes),
        "indexes": indexes,
        "degraded_indexes": [row for row in indexes if row["health_status"] != "healthy"],
        "provider_totals": _provider_totals(indexes),
        "rebuilds": [row for row in indexes if row["rebuild_progress"] > 0 and row["rebuild_progress"] < 1],
        "next_actions": _next_actions(indexes),
        "metadata": _metadata(payload, indexes, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _indexes(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("indexes") if isinstance(payload.get("indexes"), list) else payload.get("embedding_indexes")
    rows = [_index(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["health_status"]], row["index_name"], row["provider"], row["model"]))
    return rows


def _index(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    expected_dimension = _int(item.get("expected_dimension", item.get("dimension")))
    actual_dimension = _int(item.get("actual_dimension", item.get("vector_dimension", expected_dimension)))
    progress = _progress(item.get("rebuild_progress", item.get("progress")))
    stale = _bool(item.get("stale"))
    degraded = _bool(item.get("degraded"))
    orphaned = _int(item.get("orphaned_entity_count", item.get("orphaned_entities")))
    status = _health(expected_dimension, actual_dimension, stale, degraded, progress, orphaned)
    return {
        "index_name": _text(item.get("index_name") or item.get("name")) or f"index-{index}",
        "provider": _text(item.get("provider")) or "unknown-provider",
        "model": _text(item.get("model")) or "unknown-model",
        "vector_count": _int(item.get("vector_count", item.get("vectors"))),
        "expected_dimension": expected_dimension,
        "actual_dimension": actual_dimension,
        "dimension_mismatch": bool(expected_dimension and actual_dimension and expected_dimension != actual_dimension),
        "orphaned_entity_count": orphaned,
        "stale": stale,
        "degraded": degraded,
        "rebuild_progress": progress,
        "health_status": status,
        "last_built_at": item.get("last_built_at") or item.get("updated_at"),
    }


def _health(expected: int, actual: int, stale: bool, degraded: bool, progress: float, orphaned: int) -> str:
    if expected and actual and expected != actual:
        return "dimension_mismatch"
    if degraded or orphaned:
        return "degraded"
    if stale:
        return "stale"
    if 0 < progress < 1:
        return "rebuilding"
    return "healthy"


def _summary(indexes: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["health_status"] for row in indexes)
    overall = "healthy"
    for status in STATUS_RANK:
        if counts[status]:
            overall = status
            break
    return {
        "index_count": len(indexes),
        "overall_status": overall,
        "degraded_count": len([row for row in indexes if row["health_status"] != "healthy"]),
        "dimension_mismatch_count": counts["dimension_mismatch"],
        "vector_count": sum(row["vector_count"] for row in indexes),
    }


def _provider_totals(indexes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in indexes:
        grouped[(row["provider"], row["model"])].append(row)
    rows = [{"provider": provider, "model": model, "index_count": len(items), "vector_count": sum(item["vector_count"] for item in items)} for (provider, model), items in grouped.items()]
    rows.sort(key=lambda row: (row["provider"], row["model"]))
    return rows


def _next_actions(indexes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": f"repair-{row['index_name']}", "index_name": row["index_name"], "action": f"Resolve {row['health_status']} embedding index"} for row in indexes if row["health_status"] != "healthy"]


def _metadata(payload: Mapping[str, Any], indexes: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "index_count": len(indexes)}


def _progress(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number = number / 100
    return round(min(max(number, 0.0), 1.0), 4)


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
