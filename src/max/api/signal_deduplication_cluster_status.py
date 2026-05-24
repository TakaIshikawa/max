"""JSON API renderer for signal deduplication cluster status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import as_list, datetime_to_string, float_or_zero, int_or_zero, mapping, source_metadata

SCHEMA_VERSION = "max.api.signal_deduplication_cluster_status.v1"
KIND = "max.api.signal_deduplication_cluster_status"
STATUS_RANK = {"crowded": 0, "watch": 1, "healthy": 2}


def signal_deduplication_cluster_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    clusters = _clusters(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(clusters),
        "clusters": clusters,
        "status_totals": _status_totals(clusters),
        "source_totals": _source_totals(clusters),
        "crowded_clusters": [row for row in clusters if row["status"] == "crowded"],
        "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, cluster_count=len(clusters)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _clusters(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("clusters") if isinstance(payload.get("clusters"), list) else payload.get("deduplication_clusters")
    rows = [_cluster(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["duplicate_ratio"], row["cluster_id"]))


def _cluster(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    signal_count = _int(item.get("signal_count", item.get("signals")))
    duplicate_count = min(_int(item.get("duplicate_count", item.get("duplicates"))), signal_count) if signal_count else _int(item.get("duplicate_count", item.get("duplicates")))
    source_count = _int(item.get("source_count")) or len(_strings(item.get("sources")))
    raw_coverage = item.get("source_coverage", item.get("coverage"))
    coverage = _ratio(raw_coverage) if raw_coverage is not None else 1.0
    if raw_coverage is None and source_count:
        coverage = _clamp(source_count / max(signal_count, 1))
    duplicate_ratio = _ratio(item.get("duplicate_ratio"))
    if duplicate_ratio == 0.0 and signal_count:
        duplicate_ratio = _clamp(duplicate_count / signal_count)
    status = "crowded" if duplicate_ratio >= 0.5 or duplicate_count >= 10 else ("watch" if duplicate_ratio >= 0.2 or coverage < 0.5 else "healthy")
    return {
        "cluster_id": _text(item.get("cluster_id") or item.get("id")) or f"cluster-{index}",
        "canonical_signal_id": _text(item.get("canonical_signal_id") or item.get("canonical_id")) or f"signal-{index}",
        "profile": _text(item.get("profile")) or "unknown-profile",
        "source_count": source_count,
        "sources": _strings(item.get("sources")),
        "signal_count": signal_count,
        "duplicate_count": duplicate_count,
        "duplicate_ratio": duplicate_ratio,
        "source_coverage": coverage,
        "status": status,
    }


def _summary(clusters: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in clusters)
    total_signals = sum(row["signal_count"] for row in clusters)
    return {
        "cluster_count": len(clusters),
        "signal_count": total_signals,
        "duplicate_count": sum(row["duplicate_count"] for row in clusters),
        "healthy_count": counts["healthy"],
        "watch_count": counts["watch"],
        "crowded_count": counts["crowded"],
        "duplicate_ratio": _clamp(sum(row["duplicate_count"] for row in clusters) / total_signals) if total_signals else 0.0,
    }


def _status_totals(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in clusters)
    return [{"status": status, "cluster_count": counts[status]} for status in ("crowded", "watch", "healthy")]


def _source_totals(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cluster in clusters:
        for source in cluster["sources"] or ["unknown-source"]:
            grouped[source].append(cluster)
    return [{"source": source, "cluster_count": len(items), "duplicate_count": sum(item["duplicate_count"] for item in items)} for source, items in sorted(grouped.items())]


def _ratio(value: Any) -> float:
    return _clamp(float_or_zero(value))


def _clamp(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 4)


def _int(value: Any) -> int:
    return max(0, int_or_zero(value))


def _strings(value: Any) -> list[str]:
    return sorted({_text(item) for item in as_list(value) if _text(item)})


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
