"""JSON API renderer for pipeline stage latency status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.pipeline_stage_latency_status.v1"
KIND = "max.api.pipeline_stage_latency_status"
STATUS_RANK = {"critical": 0, "warning": 1, "missing": 2, "healthy": 3}


def pipeline_stage_latency_status_to_json(payload: Mapping[str, Any]) -> str:
    stages = _stages(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(stages),
        "stages": stages,
        "sla_breaches": [row for row in stages if row["status"] in {"critical", "warning"}],
        "slowest_stage": _slowest(stages),
        "metadata": source_metadata(payload, stage_count=len(stages)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _stages(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [_stage(item, index, payload) for index, item in enumerate(list_of_maps(payload.get("stages") or payload.get("stage_latencies")), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["stage"]))
    return rows


def _stage(item: Mapping[str, Any], index: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    p50 = _latency(item, "p50_ms")
    p95 = _latency(item, "p95_ms")
    p99 = _latency(item, "p99_ms")
    warning = float_or_zero(item.get("warning_threshold_ms", payload.get("warning_threshold_ms", 800)))
    critical = float_or_zero(item.get("critical_threshold_ms", payload.get("critical_threshold_ms", 1200)))
    missing = not any(key in item for key in ("p50_ms", "p95_ms", "p99_ms", "latency_ms", "duration_ms"))
    if missing:
        status = "missing"
    elif critical and p95 >= critical:
        status = "critical"
    elif warning and p95 >= warning:
        status = "warning"
    else:
        status = "healthy"
    return {
        "stage": _text(item.get("stage") or item.get("name")) or f"stage-{index}",
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "sample_count": int_or_zero(item.get("sample_count", item.get("samples"))),
        "warning_threshold_ms": warning,
        "critical_threshold_ms": critical,
        "sla_breached": status in {"critical", "warning"},
        "status": status,
    }


def _latency(item: Mapping[str, Any], key: str) -> float:
    fallback = item.get("latency_ms", item.get("duration_ms"))
    return round(max(0.0, float_or_zero(item.get(key, fallback))), 2)


def _summary(stages: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in stages)
    status = "no_data" if not stages else ("critical" if counts["critical"] else ("warning" if counts["warning"] or counts["missing"] else "healthy"))
    return {
        "status": status,
        "stage_count": len(stages),
        "critical_count": counts["critical"],
        "warning_count": counts["warning"],
        "missing_count": counts["missing"],
        "sla_breach_count": counts["critical"] + counts["warning"],
    }


def _slowest(stages: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not stages:
        return None
    row = max(stages, key=lambda item: (item["p95_ms"], item["stage"]))
    return {"stage": row["stage"], "p95_ms": row["p95_ms"], "status": row["status"]}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
