"""Embedding cluster coverage export report."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

SCHEMA_VERSION = "max.embedding_cluster_coverage_report.v1"
KIND = "max.embedding_cluster_coverage_report"


def generate_embedding_cluster_coverage_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    unclustered = 0
    clusters: Counter[str] = Counter()
    for raw in records:
        total += 1
        cluster_id = _text(raw.get("cluster_id") or raw.get("embedding_cluster_id") or raw.get("cluster"))
        if cluster_id:
            clusters[cluster_id] += 1
        else:
            unclustered += 1
    singleton_count = sum(1 for count in clusters.values() if count == 1)
    largest = max(clusters.values(), default=0)
    unclustered_ratio = _ratio(unclustered, total)
    largest_cluster_share = _ratio(largest, total)
    risk = _risk(unclustered_ratio, singleton_count, largest_cluster_share)
    rows = [{"cluster_id": cluster_id, "item_count": count, "item_share": _ratio(count, total), "is_singleton": count == 1} for cluster_id, count in sorted(clusters.items())]
    rows.sort(key=lambda row: (-row["item_count"], row["cluster_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"item_count": total, "cluster_count": len(clusters), "unclustered_item_count": unclustered, "unclustered_item_ratio": unclustered_ratio, "singleton_cluster_count": singleton_count, "largest_cluster_share": largest_cluster_share, "coverage_risk": risk}, "rows": rows}


def _risk(unclustered_ratio: float, singleton_count: int, largest_share: float) -> str:
    if unclustered_ratio >= 0.4 or largest_share >= 0.75:
        return "high"
    if unclustered_ratio >= 0.15 or singleton_count >= 3 or largest_share >= 0.5:
        return "medium"
    return "low"


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
