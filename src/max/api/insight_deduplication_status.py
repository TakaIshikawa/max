"""JSON API renderer for insight deduplication status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.insight_deduplication_status.v1"
KIND = "max.api.insight_deduplication_status"


def insight_deduplication_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    threshold = _score(payload.get("review_threshold", payload.get("similarity_threshold", 0.9)))
    clusters = _clusters(payload, threshold)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(clusters, threshold),
        "clusters": clusters,
        "review_needed": [row for row in clusters if row["review_needed"]],
        "profile_totals": _totals(clusters, "profile"),
        "category_totals": _totals(clusters, "category"),
        "metadata": _metadata(payload, clusters, threshold, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _clusters(payload: Mapping[str, Any], threshold: float) -> list[dict[str, Any]]:
    source = payload.get("clusters") if isinstance(payload.get("clusters"), list) else payload.get("dedupe_clusters")
    rows = [_cluster(item, index, threshold) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (not row["review_needed"], -row["duplicate_count"], row["cluster_id"], row["canonical_insight_id"]))
    return rows


def _cluster(item: Mapping[str, Any], index: int, threshold: float) -> dict[str, Any]:
    duplicate_ids = sorted(str(value) for value in _as_list(item.get("duplicate_ids") or item.get("duplicates")) if value not in (None, ""))
    duplicate_count = _int(item.get("duplicate_count", len(duplicate_ids)))
    score = _score(item.get("similarity_score", item.get("score")))
    canonical_id = _text(item.get("canonical_insight_id") or item.get("canonical_id")) or f"canonical-{index}"
    explicit_review = item.get("review_needed")
    review_needed = _bool(explicit_review) if explicit_review is not None else score < threshold or duplicate_count > 0 and not canonical_id
    return {
        "cluster_id": _text(item.get("cluster_id") or item.get("id")) or f"cluster-{index}",
        "canonical_insight_id": canonical_id,
        "profile": _text(item.get("profile")) or "unknown-profile",
        "category": _text(item.get("category")) or "uncategorized",
        "duplicate_count": duplicate_count,
        "duplicate_ids": duplicate_ids,
        "similarity_score": score,
        "threshold": threshold,
        "review_needed": review_needed,
    }


def _summary(clusters: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    return {
        "cluster_count": len(clusters),
        "duplicate_count": sum(row["duplicate_count"] for row in clusters),
        "review_needed_count": sum(1 for row in clusters if row["review_needed"]),
        "canonical_insight_count": len({row["canonical_insight_id"] for row in clusters}),
        "review_threshold": threshold,
    }


def _totals(clusters: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cluster in clusters:
        grouped[cluster[field]].append(cluster)
    rows = [
        {
            field: value,
            "cluster_count": len(items),
            "duplicate_count": sum(item["duplicate_count"] for item in items),
            "review_needed_count": sum(1 for item in items if item["review_needed"]),
        }
        for value, items in grouped.items()
    ]
    rows.sort(key=lambda row: (-row["review_needed_count"], -row["duplicate_count"], row[field]))
    return rows


def _metadata(payload: Mapping[str, Any], clusters: list[dict[str, Any]], threshold: float, as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "cluster_count": len(clusters), "review_threshold": threshold}


def _score(value: Any) -> float:
    try:
        return round(min(max(float(value), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
