"""JSON API renderer for buildable unit duplicate risk status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.buildable_unit_duplicate_risk_status.v1"
KIND = "max.api.buildable_unit_duplicate_risk_status"
STATUS_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def buildable_unit_duplicate_risk_status_to_json(payload: Mapping[str, Any]) -> str:
    clusters = [_cluster(item, index, payload) for index, item in enumerate(list_of_maps(payload.get("clusters") or payload.get("duplicates")), start=1)]
    clusters = [row for row in clusters if row["similarity_score"] >= row["warning_threshold"]]
    clusters.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["similarity_score"], row["representative_title"]))
    status = "critical" if any(row["status"] == "critical" for row in clusters) else ("warning" if clusters else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "cluster_count": len(clusters), "affected_unit_count": len({unit for row in clusters for unit in row["unit_ids"]})}, "duplicate_clusters": clusters, "highest_similarity_pairs": _pairs(clusters), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _cluster(item: Mapping[str, Any], index: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    score = round(max(0.0, min(float_or_zero(item.get("similarity_score", item.get("score"))), 1.0)), 4)
    warning = float_or_zero(item.get("warning_threshold", payload.get("warning_threshold", 0.8)))
    critical = float_or_zero(item.get("critical_threshold", payload.get("critical_threshold", 0.92)))
    return {"cluster_id": _text(item.get("cluster_id") or item.get("id")) or f"cluster-{index}", "unit_ids": strings(item.get("unit_ids") or item.get("units")), "similarity_score": score, "representative_title": _text(item.get("representative_title") or item.get("title")) or "Untitled unit", "warning_threshold": warning, "critical_threshold": critical, "status": "critical" if score >= critical else "warning"}


def _pairs(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"unit_ids": row["unit_ids"][:2], "similarity_score": row["similarity_score"], "cluster_id": row["cluster_id"]} for row in clusters if len(row["unit_ids"]) >= 2]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
