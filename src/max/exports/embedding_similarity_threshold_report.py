"""Embedding similarity threshold export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.embedding_similarity_threshold_report.v1"
KIND = "max.embedding_similarity_threshold_report"
_STATUS_ORDER = {"loose": 0, "strict": 1, "tuned": 2}


def generate_embedding_similarity_threshold_report(samples: Iterable[dict[str, Any]], *, default_threshold: float = 0.8, near_miss_band: float = 0.05, collision_band: float = 0.1) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"count": 0, "threshold": _ratio(default_threshold), "matches": 0, "near": 0, "collisions": 0, "similarity": 0.0})
    for raw in samples:
        if not isinstance(raw, dict):
            continue
        key = (_text(raw.get("index_name") or raw.get("index")) or "unknown-index", _text(raw.get("profile") or raw.get("profile_id")) or "default")
        group = groups[key]
        threshold = _ratio(raw.get("threshold") or group["threshold"])
        similarity = _ratio(raw.get("similarity") or raw.get("score"))
        group["threshold"] = threshold
        group["count"] += 1
        group["similarity"] += similarity
        if similarity >= threshold:
            group["matches"] += 1
        elif similarity >= threshold - near_miss_band:
            group["near"] += 1
        if similarity >= threshold + collision_band or raw.get("collision"):
            group["collisions"] += 1
    rows = []
    for (index_name, profile), group in groups.items():
        rows.append({"index_name": index_name, "profile": profile, "threshold": group["threshold"], "sample_count": group["count"], "match_count": group["matches"], "near_miss_count": group["near"], "collision_count": group["collisions"], "average_similarity": round(group["similarity"] / group["count"], 4) if group["count"] else 0.0, "status": "loose" if group["collisions"] else ("strict" if group["near"] > group["matches"] else "tuned")})
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["index_name"].casefold(), row["profile"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": rows[0]["status"] if rows else "tuned", "group_count": len(rows), "match_count": sum(row["match_count"] for row in rows), "near_miss_count": sum(row["near_miss_count"] for row in rows), "collision_count": sum(row["collision_count"] for row in rows)}, "rows": rows}


def _ratio(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
