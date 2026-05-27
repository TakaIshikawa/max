"""JSON API renderer for LLM prompt cache health status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.llm_prompt_cache_health_status.v1"
KIND = "max.api.llm_prompt_cache_health_status"


def llm_prompt_cache_health_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    rows = _caches(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "caches": rows, "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, request_count=sum(row["request_count"] for row in rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _caches(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("caches") if isinstance(payload.get("caches"), list) else payload.get("metrics")
    rows = [_cache(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (row["hit_rate"], -row["stale_entry_count"], row["provider"], row["model"], row["profile"]))


def _cache(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    hits = max(0, int_or_zero(item.get("hits", item.get("cache_hits"))))
    misses = max(0, int_or_zero(item.get("misses", item.get("cache_misses"))))
    requests = max(hits + misses, int_or_zero(item.get("request_count", item.get("requests"))))
    hit_rate = round(hits / requests, 4) if requests else 0.0
    stale = max(0, int_or_zero(item.get("stale_entry_count", item.get("stale_entries"))))
    status = "stale" if stale else ("cold" if hit_rate < 0.5 and requests else "healthy")
    return {"provider": _text(item.get("provider")) or "unknown-provider", "model": _text(item.get("model")) or "unknown-model", "profile": _bucket(item.get("profile"), f"profile_{index}"), "request_count": requests, "hit_count": hits, "miss_count": misses, "hit_rate": hit_rate, "miss_rate": round(1 - hit_rate, 4) if requests else 0.0, "stale_entry_count": stale, "estimated_saved_tokens": max(0, int_or_zero(item.get("estimated_saved_tokens", item.get("saved_tokens")))), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    requests = sum(row["request_count"] for row in rows)
    hits = sum(row["hit_count"] for row in rows)
    stale = sum(row["stale_entry_count"] for row in rows)
    hit_rate = round(hits / requests, 4) if requests else 0.0
    return {"status": "stale" if stale else ("cold" if hit_rate < 0.5 and requests else "healthy"), "request_count": requests, "hit_rate": hit_rate, "stale_entry_count": stale, "estimated_saved_tokens": sum(row["estimated_saved_tokens"] for row in rows)}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
