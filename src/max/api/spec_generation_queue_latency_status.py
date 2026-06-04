"""JSON API renderer for spec generation queue latency status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import list_of_maps, mapping, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.spec_generation_queue_latency_status.v1"
KIND = "max.api.spec_generation_queue_latency_status"
ACTIVE = {"queued", "running"}
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def spec_generation_queue_latency_status_to_json(records: Any, *, now: str | datetime | None = None, warning_minutes: int = 30, critical_minutes: int = 120) -> str:
    payload = mapping(records)
    source = payload.get("jobs") or payload.get("records") or payload.get("items") or (records if isinstance(records, list) else [])
    effective_now = parse_datetime(now) or parse_datetime(payload.get("now")) or datetime.now().astimezone()
    jobs = [_job(item, index, effective_now) for index, item in enumerate(list_of_maps(source), start=1)]
    active = [job for job in jobs if job["state"] in ACTIVE]
    latencies = [job["historical_latency_minutes"] for job in jobs if job["historical_latency_minutes"] is not None]
    oldest = max((job["active_age_minutes"] for job in active), default=0.0)
    p95 = _percentile(latencies, 0.95)
    status = "critical" if oldest >= critical_minutes else ("warning" if oldest >= warning_minutes or p95 >= warning_minutes else "ok")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": status, "summary": {"job_count": len(jobs), "active_backlog_count": len(active), "oldest_queued_age_minutes": round(oldest, 2), "p95_queue_latency_minutes": round(p95, 2), "status": status}, "jobs": sorted(jobs, key=lambda row: (row["state"] not in ACTIVE, -row["active_age_minutes"], row["job_id"])), "metadata": source_metadata(payload, job_count=len(jobs))}, indent=2, sort_keys=True)


def _job(item: Mapping[str, Any], index: int, now: datetime) -> dict[str, Any]:
    queued = parse_datetime(item.get("queued_at") or item.get("created_at"))
    started = parse_datetime(item.get("started_at"))
    state = _text(item.get("status") or item.get("state")).casefold() or "queued"
    active_age = max((now - queued).total_seconds() / 60, 0.0) if queued and state in ACTIVE else 0.0
    historical = max((started - queued).total_seconds() / 60, 0.0) if queued and started else None
    return {"job_id": _text(item.get("job_id") or item.get("id")) or f"job-{index}", "state": state, "queued_at": item.get("queued_at") or item.get("created_at"), "started_at": item.get("started_at"), "active_age_minutes": round(active_age, 2), "historical_latency_minutes": round(historical, 2) if historical is not None else None}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
