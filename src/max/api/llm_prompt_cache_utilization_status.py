"""JSON API renderer for LLM prompt cache utilization status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.llm_prompt_cache_utilization_status.v1"
KIND = "max.api.llm_prompt_cache_utilization_status"


def llm_prompt_cache_utilization_status_to_json(payload: Mapping[str, Any]) -> str:
    min_warning = float_or_zero(payload.get("warning_min_hit_rate")) or 0.5
    min_critical = float_or_zero(payload.get("critical_min_hit_rate")) or 0.25
    stale_critical_ratio = float_or_zero(payload.get("stale_critical_ratio")) or 0.5
    families = [_family(row, min_warning, min_critical, stale_critical_ratio) for row in _items(payload)]
    families.sort(key=lambda row: (_rank(row["status"]), row["prompt_family"]))
    summary = _summary(families)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "families": families, "metadata": source_metadata(payload, family_count=len(families))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("families")) or list_of_maps(payload.get("prompts")) or list_of_maps(payload.get("items"))


def _family(row: Mapping[str, Any], min_warning: float, min_critical: float, stale_critical_ratio: float) -> dict[str, Any]:
    hits = max(0, int_or_zero(row.get("cache_hits")))
    misses = max(0, int_or_zero(row.get("cache_misses")))
    stale = max(0, int_or_zero(row.get("stale_hits")))
    activity = hits + misses
    hit_rate = round(hits / activity, 4) if activity else 0.0
    stale_ratio = round(stale / hits, 4) if hits else (1.0 if stale else 0.0)
    if activity == 0:
        status = "no_activity"
    elif stale_ratio >= stale_critical_ratio or hit_rate < min_critical:
        status = "critical"
    elif hit_rate < min_warning or stale:
        status = "warning"
    else:
        status = "ok"
    return {"prompt_family": _bucket(row.get("prompt_family") or row.get("family"), "unknown_family"), "cache_hits": hits, "cache_misses": misses, "hit_rate": hit_rate, "stale_hits": stale, "stale_ratio": stale_ratio, "avoided_tokens": max(0, int_or_zero(row.get("tokens_saved") or row.get("avoided_tokens"))), "wasted_tokens": stale, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    hits = sum(row["cache_hits"] for row in rows)
    misses = sum(row["cache_misses"] for row in rows)
    activity = hits + misses
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "hit_rate": round(hits / activity, 4) if activity else 0.0, "cache_hits": hits, "cache_misses": misses, "avoided_tokens": sum(row["avoided_tokens"] for row in rows), "wasted_tokens": sum(row["wasted_tokens"] for row in rows), "cacheable_family_count": len(rows), "critical_count": critical, "warning_count": warning}


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "no_activity": 2, "ok": 3}.get(status, 4)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
