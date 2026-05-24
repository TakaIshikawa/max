"""JSON API renderer for pipeline stage SLA status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.pipeline_stage_sla_status.v1"
KIND = "max.api.pipeline_stage_sla_status"
STATUS_RANK = {"stalled": 0, "breached": 1, "warning": 2, "healthy": 3}


def pipeline_stage_sla_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    stages = _stages(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(stages),
        "stages": stages,
        "breached_stages": [row for row in stages if row["status"] in {"breached", "stalled"}],
        "stage_totals": _totals(stages, "stage"),
        "run_totals": _totals(stages, "run_id"),
        "metadata": _metadata(payload, stages, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _stages(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("stages") if isinstance(payload.get("stages"), list) else payload.get("pipeline_stages")
    rows = [_stage(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["run_id"], row["stage"]))
    return rows


def _stage(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    duration = _float(item.get("duration_seconds", item.get("duration")))
    sla = _float(item.get("sla_seconds", item.get("sla")))
    queue = _float(item.get("queue_seconds", item.get("queue")))
    stalled = _bool(item.get("stalled")) or _text(item.get("state")).lower() == "stalled"
    status = "stalled" if stalled else ("breached" if sla and duration > sla else ("warning" if sla and duration >= sla * 0.8 else "healthy"))
    return {
        "run_id": _text(item.get("run_id") or item.get("run")) or f"run-{index}",
        "stage": _text(item.get("stage") or item.get("name")) or f"stage-{index}",
        "duration_seconds": duration,
        "sla_seconds": sla,
        "retry_count": _int(item.get("retry_count", item.get("retries"))),
        "queue_seconds": queue,
        "status": status,
    }


def _summary(stages: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in stages)
    return {"stage_count": len(stages), "breached_count": counts["breached"], "stalled_count": counts["stalled"], "warning_count": counts["warning"], "max_duration_seconds": max((row["duration_seconds"] for row in stages), default=0.0)}


def _totals(stages: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in stages:
        grouped[row[field]].append(row)
    return [{field: key, "stage_count": len(items), "breached_count": sum(1 for item in items if item["status"] in {"breached", "stalled"})} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], stages: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "stage_count": len(stages)}


def _float(value: Any) -> float:
    try:
        return round(max(0.0, float(value or 0)), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "stalled"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
