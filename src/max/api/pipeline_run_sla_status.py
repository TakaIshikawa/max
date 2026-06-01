"""JSON API renderer for pipeline run SLA status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, parse_datetime, source_metadata, strings

SCHEMA_VERSION = "max.api.pipeline_run_sla_status.v1"
KIND = "max.api.pipeline_run_sla_status"


def pipeline_run_sla_status_to_json(payload: Mapping[str, Any]) -> str:
    threshold = float_or_zero(payload.get("duration_sla_seconds") or payload.get("sla_seconds") or 3600)
    rows = [_run(row, i, threshold) for i, row in enumerate(list_of_maps(payload.get("runs") or payload.get("rows")), start=1)]
    breached = [row for row in rows if row["breached"]]
    rate = round(len(breached) / len(rows), 4) if rows else 0.0
    status = "critical" if rate > 0.5 and breached else ("warning" if breached else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "total_runs": len(rows), "breached_runs": len(breached), "breach_rate": rate, "missed_stage_counts": dict(sorted(Counter(stage for row in rows for stage in row["failed_or_missing_stages"]).items())), "worst_runs": sorted(breached, key=lambda row: (-row["sla_overage_seconds"], row["run_id"]))[:10], "overall_status": status, "runs": rows, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _run(item: Mapping[str, Any], index: int, threshold: float) -> dict[str, Any]:
    duration = item.get("duration_seconds")
    if duration is None:
        started = parse_datetime(item.get("started_at"))
        finished = parse_datetime(item.get("finished_at"))
        duration = (finished - started).total_seconds() if started and finished else 0
    duration_value = float_or_zero(duration)
    stages = strings(item.get("failed_or_missing_stages") or item.get("missed_stages"))
    completion_breach = _text(item.get("status")).casefold() not in {"completed", "success", "succeeded", ""}
    breached = duration_value > threshold or completion_breach or bool(stages)
    return {"run_id": _text(item.get("run_id") or item.get("id")) or f"run-{index}", "profile": _text(item.get("profile")) or "default", "stage": _text(item.get("stage")) or "pipeline", "duration_seconds": duration_value, "duration_sla_seconds": threshold, "sla_overage_seconds": max(round(duration_value - threshold, 2), 0), "status": _text(item.get("status")) or "completed", "failed_or_missing_stages": stages, "breached": breached}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
