"""JSON API renderer for source fetch latency."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.source_fetch_latency.v1"
KIND = "max.api.source_fetch_latency"
STATUS_RANK = {"timed_out": 0, "slow": 1, "healthy": 2}


def source_fetch_latency_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    sources = _sources(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(sources),
        "sources": sources,
        "slowest_sources": sorted(sources, key=lambda row: (-row["max_latency_ms"], row["source"]))[:5],
        "metadata": _metadata(payload, sources, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _sources(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    default_sla = _number(payload.get("sla_ms", payload.get("default_sla_ms", 1000)))
    source = payload.get("sources") if isinstance(payload.get("sources"), list) else payload.get("fetches")
    rows = [_source(item, index, default_sla) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["p95_latency_ms"], row["source"]))
    return rows


def _source(item: Mapping[str, Any], index: int, default_sla: float) -> dict[str, Any]:
    latencies = sorted(_number(value) for value in item.get("latencies_ms", item.get("latencies", [])) if _number(value) >= 0) if isinstance(item.get("latencies_ms", item.get("latencies", [])), list) else []
    timeout_count = _int(item.get("timeout_count", item.get("timeouts"))) + sum(1 for value in item.get("events", []) if isinstance(value, Mapping) and _bool(value.get("timed_out")))
    sla = _number(item.get("sla_ms", default_sla)) or default_sla
    p50 = _percentile(latencies, 0.5)
    p95 = _percentile(latencies, 0.95)
    max_latency = max(latencies) if latencies else 0.0
    status = "timed_out" if timeout_count else ("slow" if sla and p95 > sla else "healthy")
    return {"source": _text(item.get("source") or item.get("name")) or f"source-{index}", "adapter": _text(item.get("adapter") or item.get("adapter_name")) or "unknown-adapter", "sla_ms": sla, "sample_count": len(latencies), "p50_latency_ms": p50, "p95_latency_ms": p95, "max_latency_ms": max_latency, "timeout_count": timeout_count, "status": status}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = round((len(values) - 1) * percentile)
    return round(values[index], 3)


def _summary(sources: list[dict[str, Any]]) -> dict[str, Any]:
    status = "timed_out" if any(row["status"] == "timed_out" for row in sources) else ("slow" if any(row["status"] == "slow" for row in sources) else "healthy")
    return {"status": status, "source_count": len(sources), "slow_count": sum(1 for row in sources if row["status"] == "slow"), "timed_out_count": sum(1 for row in sources if row["status"] == "timed_out"), "timeout_count": sum(row["timeout_count"] for row in sources)}


def _metadata(payload: Mapping[str, Any], sources: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "source_count": len(sources)}


def _number(value: Any) -> float:
    try:
        return round(max(float(value or 0), 0.0), 3)
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


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
