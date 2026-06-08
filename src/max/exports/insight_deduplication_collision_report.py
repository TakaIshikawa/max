"""Insight deduplication collision rollup export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.insight_deduplication_collision_report.v1"
KIND = "max.insight_deduplication_collision_report"


def generate_insight_deduplication_collision_report(
    records: Iterable[dict[str, Any]],
    *,
    similarity_threshold: float = 0.9,
) -> dict[str, Any]:
    threshold = min(1.0, max(0.0, _float(similarity_threshold)))
    clusters: dict[str, list[dict[str, Any]]] = {}
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, dict):
            continue
        cluster_id = _text(raw.get("cluster_id") or raw.get("dedupe_group_id") or raw.get("duplicate_of")) or f"cluster-{index}"
        clusters.setdefault(cluster_id, []).append(_record(raw, index))

    rows = []
    for cluster_id, items in clusters.items():
        high_similarity = max((item["similarity_score"] for item in items), default=0.0) >= threshold
        reasons = _reasons(items) if high_similarity else []
        rows.append({"cluster_id": cluster_id, "insight_ids": sorted({item["insight_id"] for item in items}, key=str.lower), "insight_count": len(items), "max_similarity": max((item["similarity_score"] for item in items), default=0.0), "collision_reasons": reasons, "collision_count": len(reasons), "status": "collision" if reasons else "clean"})
    rows.sort(key=lambda row: (row["status"] != "collision", row["cluster_id"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"cluster_count": len(rows), "collision_cluster_count": sum(1 for row in rows if row["status"] == "collision"), "collision_count": sum(row["collision_count"] for row in rows), "similarity_threshold": threshold}, "rows": rows}


def _record(raw: dict[str, Any], index: int) -> dict[str, Any]:
    return {"insight_id": _text(raw.get("insight_id") or raw.get("id")) or f"insight-{index}", "theme": _text(raw.get("theme") or raw.get("topic")).lower(), "role": _text(raw.get("role") or raw.get("persona")).lower(), "sources": tuple(sorted(_items(raw.get("sources") or raw.get("source_ids")), key=str.lower)), "confidence_band": _band(raw.get("confidence_band") or raw.get("confidence")), "similarity_score": round(_float(raw.get("similarity_score") or raw.get("similarity")), 4)}


def _reasons(items: list[dict[str, Any]]) -> list[str]:
    reasons = []
    for key, reason in (("theme", "conflicting_themes"), ("role", "conflicting_roles"), ("sources", "conflicting_sources"), ("confidence_band", "conflicting_confidence_bands")):
        values = {item[key] for item in items if item[key]}
        if len(values) > 1:
            reasons.append(reason)
    return reasons


def _band(value: Any) -> str:
    if isinstance(value, int | float):
        return "high" if value >= 0.75 else ("medium" if value >= 0.5 else "low")
    return _text(value).lower()


def _items(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_text(value)] if _text(value) else []
    if isinstance(value, list | tuple | set):
        return [_text(item) for item in value if _text(item)]
    return []


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
