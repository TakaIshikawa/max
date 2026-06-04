"""JSON API renderer for embedding similarity outlier status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.embedding_similarity_outlier_status.v1"
KIND = "max.api.embedding_similarity_outlier_status"
STATUS_RANK = {"low_similarity_outlier": 0, "duplicate_risk": 1, "ok": 2}


def embedding_similarity_outlier_status_to_json(payload: Mapping[str, Any], *, low_similarity_threshold: float = 0.2, duplicate_similarity_threshold: float = 0.95) -> str:
    rows = [_row(item, index, low_similarity_threshold, duplicate_similarity_threshold) for index, item in enumerate(_items(payload), start=1)]
    rows = sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["nearest_similarity"] if row["status"] == "low_similarity_outlier" else -row["nearest_similarity"], row["item_id"]))
    worst = next((row for row in rows if row["status"] == "low_similarity_outlier"), None)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"item_count": len(rows), "outlier_count": sum(1 for row in rows if row["status"] == "low_similarity_outlier"), "duplicate_risk_count": sum(1 for row in rows if row["status"] == "duplicate_risk"), "worst_item_id": worst["item_id"] if worst else None}, "embedding_rows": rows, "metadata": source_metadata(payload, item_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("embeddings") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, low: float, duplicate: float) -> dict[str, Any]:
    similarity = min(max(float_or_zero(item.get("nearest_similarity")), 0.0), 1.0)
    status = "low_similarity_outlier" if similarity <= low else "duplicate_risk" if similarity >= duplicate else "ok"
    return {"item_id": _text(item.get("item_id") or item.get("id")) or f"item-{index}", "item_type": _text(item.get("item_type")) or None, "cluster_id": _text(item.get("cluster_id")) or None, "nearest_similarity": round(similarity, 4), "status": status, "created_at": _text(item.get("created_at")) or None}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
