"""Embedding cache hit rate export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.embedding_cache_hit_rate_report.v1"
KIND = "max.embedding_cache_hit_rate_report"


def generate_embedding_cache_hit_rate_report(records: Iterable[dict[str, Any]], *, cold_threshold: float = 0.8) -> dict[str, Any]:
    threshold = _ratio(cold_threshold)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        namespace = _text(raw.get("namespace") or raw.get("cache_namespace")) or "default"
        model = _text(raw.get("model") or raw.get("embedding_model")) or "unknown-model"
        group = groups.setdefault((namespace, model), {"hits": 0, "misses": 0, "latest": ""})
        group["hits"] += _int(raw.get("hit_count") or raw.get("hits"))
        group["misses"] += _int(raw.get("miss_count") or raw.get("misses"))
        if not raw.get("hit_count") and not raw.get("miss_count") and not raw.get("hits") and not raw.get("misses"):
            if _hit(raw):
                group["hits"] += 1
            else:
                group["misses"] += 1
        lookup_at = _text(raw.get("lookup_at") or raw.get("created_at") or raw.get("timestamp"))
        if lookup_at > group["latest"]:
            group["latest"] = lookup_at
    rows = []
    for (namespace, model), group in groups.items():
        total = group["hits"] + group["misses"]
        hit_rate = round(group["hits"] / total, 4) if total else 0.0
        rows.append({"namespace": namespace, "model": model, "hit_count": group["hits"], "miss_count": group["misses"], "total_count": total, "hit_rate": hit_rate, "latest_lookup_at": group["latest"] or None, "status": "cold" if hit_rate < threshold else "warm"})
    rows.sort(key=lambda row: (row["namespace"].lower(), row["model"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "cold_count": sum(1 for row in rows if row["status"] == "cold"), "cold_threshold": threshold}, "rows": rows}


def _hit(raw: dict[str, Any]) -> bool:
    value = raw.get("hit") if "hit" in raw else raw.get("cache_hit")
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "hit"}


def _ratio(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.8


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
