"""JSON API renderer for pipeline stage latency."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, parse_datetime, source_metadata


SCHEMA_VERSION = "max.api.pipeline_stage_latency.v1"
KIND = "max.api.pipeline_stage_latency"
DEFAULT_SLOW_THRESHOLD_MS = 1000


def pipeline_stage_latency_to_json(payload: Mapping[str, Any]) -> str:
    stages = _stages(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "run_summary": _run_summary(payload, stages),
        "stages": stages,
        "bottlenecks": _bottlenecks(payload, stages),
        "retry_latency": _retry_latency(payload, stages),
        "threshold_violations": _threshold_violations(payload, stages),
        "metadata": source_metadata(payload, stage_count=len(stages)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _stages(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("stages")
    if not isinstance(source, list):
        source = payload.get("stage_timings")
    rows = [
        _stage(item, index, int_or_zero(payload.get("slow_threshold_ms", DEFAULT_SLOW_THRESHOLD_MS)))
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (str(row["stage_name"]), str(row["stage_id"])))


def _stage(item: Mapping[str, Any], index: int, default_threshold: int) -> dict[str, Any]:
    duration_ms = item.get("duration_ms")
    if duration_ms is None:
        duration_ms = _duration_ms(item.get("started_at"), item.get("completed_at"))
    threshold = int_or_zero(item.get("slow_threshold_ms", item.get("threshold_ms", default_threshold)))
    duration = int_or_zero(duration_ms)
    return {
        "stage_id": item.get("stage_id") or item.get("id") or f"S{index}",
        "stage_name": item.get("stage_name") or item.get("name") or item.get("stage") or f"stage-{index}",
        "status": item.get("status") or "unknown",
        "started_at": item.get("started_at"),
        "completed_at": item.get("completed_at"),
        "duration_ms": duration,
        "queue_ms": int_or_zero(item.get("queue_ms")),
        "retry_count": int_or_zero(item.get("retry_count", item.get("retries"))),
        "slow_threshold_ms": threshold,
        "slow": duration > threshold if threshold else False,
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _run_summary(payload: Mapping[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
    run = mapping(payload.get("run"))
    source = mapping(payload.get("run_summary"))
    return {
        "run_id": source.get("run_id") or source.get("id") or run.get("id"),
        "status": source.get("status") or run.get("status"),
        "total_duration_ms": int_or_zero(source.get("total_duration_ms", sum(stage["duration_ms"] for stage in stages))),
        "total_queue_ms": int_or_zero(source.get("total_queue_ms", sum(stage["queue_ms"] for stage in stages))),
        "stage_count": int_or_zero(source.get("stage_count", len(stages))),
    }


def _bottlenecks(payload: Mapping[str, Any], stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("bottlenecks"))
    if explicit:
        rows = [
            {
                "stage_id": item.get("stage_id") or item.get("id") or f"B{index}",
                "stage_name": item.get("stage_name") or item.get("name") or item.get("stage"),
                "duration_ms": int_or_zero(item.get("duration_ms")),
            }
            for index, item in enumerate(explicit, start=1)
        ]
    else:
        rows = [{"stage_id": stage["stage_id"], "stage_name": stage["stage_name"], "duration_ms": stage["duration_ms"]} for stage in stages]
    return sorted(rows, key=lambda row: (-int_or_zero(row["duration_ms"]), str(row["stage_name"] or "")))


def _retry_latency(payload: Mapping[str, Any], stages: list[dict[str, Any]]) -> dict[str, int]:
    explicit = mapping(payload.get("retry_latency"))
    retried = [stage for stage in stages if stage["retry_count"]]
    return {
        "retried_stage_count": int_or_zero(explicit.get("retried_stage_count", len(retried))),
        "total_retry_count": int_or_zero(explicit.get("total_retry_count", sum(stage["retry_count"] for stage in stages))),
        "duration_ms": int_or_zero(explicit.get("duration_ms", sum(stage["duration_ms"] for stage in retried))),
    }


def _threshold_violations(payload: Mapping[str, Any], stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("threshold_violations"))
    if explicit:
        return sorted(
            [{"stage_id": item.get("stage_id") or item.get("id") or f"V{index}", "stage_name": item.get("stage_name") or item.get("name"), "duration_ms": int_or_zero(item.get("duration_ms")), "slow_threshold_ms": int_or_zero(item.get("slow_threshold_ms", item.get("threshold_ms")))} for index, item in enumerate(explicit, start=1)],
            key=lambda row: (str(row["stage_name"] or ""), str(row["stage_id"])),
        )
    return [
        {"stage_id": stage["stage_id"], "stage_name": stage["stage_name"], "duration_ms": stage["duration_ms"], "slow_threshold_ms": stage["slow_threshold_ms"]}
        for stage in stages
        if stage["slow"]
    ]


def _duration_ms(started_at: Any, completed_at: Any) -> int:
    started = parse_datetime(started_at)
    completed = parse_datetime(completed_at)
    if started is None or completed is None:
        return 0
    return max(int((completed - started).total_seconds() * 1000), 0)
