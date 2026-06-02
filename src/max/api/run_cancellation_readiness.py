"""JSON API renderer for run cancellation readiness."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.run_cancellation_readiness.v1"
KIND = "max.api.run_cancellation_readiness"


def run_cancellation_readiness_to_json(payload: Mapping[str, Any]) -> str:
    stages = _stages(payload)
    workers = _blocking_workers(payload)
    cleanup = _cleanup_tasks(payload)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "run_summary": _run_summary(payload),
            "stage_readiness": stages,
            "blocking_workers": workers,
            "pending_cleanup_tasks": cleanup,
            "cancellation_requests": _requests(payload),
            "metadata": source_metadata(payload, stage_count=len(stages), blocking_worker_count=len(workers)),
        },
        indent=2,
        sort_keys=True,
    )


def _run_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    run = mapping(payload.get("run"))
    return {
        "run_id": run.get("run_id") or run.get("id") or payload.get("run_id"),
        "status": run.get("status") or payload.get("status") or "unknown",
        "can_cancel_cleanly": not _blocking_workers(payload) and not any(row["readiness"] == "blocked" for row in _stages(payload)),
    }


def _stages(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [_stage(item, index) for index, item in enumerate(list_of_maps(payload.get("stages")), start=1)]
    return sorted(rows, key=lambda row: (_readiness_rank(row["readiness"]), row["stage"]))


def _stage(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    readiness = str(item.get("readiness") or item.get("cancellation_state") or "").lower()
    if readiness not in {"cancellable", "draining", "blocked", "unknown"}:
        if item.get("blocked_reason"):
            readiness = "blocked"
        elif item.get("draining"):
            readiness = "draining"
        elif item.get("can_cancel") is True:
            readiness = "cancellable"
        else:
            readiness = "unknown"
    return {
        "stage": str(item.get("stage") or item.get("name") or f"stage-{index}"),
        "readiness": readiness,
        "blocked_reason": item.get("blocked_reason"),
        "active_worker_count": int(item.get("active_worker_count") or 0),
    }


def _blocking_workers(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(list_of_maps(payload.get("workers")), start=1):
        blocked_reason = item.get("blocked_reason") or item.get("cancel_blocker")
        if blocked_reason or item.get("blocking"):
            rows.append(
                {
                    "worker_id": item.get("worker_id") or item.get("id") or f"worker-{index}",
                    "stage": item.get("stage"),
                    "blocked_reason": blocked_reason or "blocking",
                }
            )
    return sorted(rows, key=lambda row: (str(row["stage"] or ""), str(row["worker_id"])))


def _cleanup_tasks(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(list_of_maps(payload.get("cleanup_tasks")), start=1):
        status = str(item.get("status") or "pending")
        if status in {"pending", "queued", "running"}:
            rows.append({"task_id": item.get("task_id") or item.get("id") or f"cleanup-{index}", "status": status, "stage": item.get("stage")})
    return sorted(rows, key=lambda row: (str(row["stage"] or ""), str(row["task_id"])))


def _requests(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            {"request_id": item.get("request_id") or item.get("id") or f"request-{index}", "requested_by": item.get("requested_by"), "status": item.get("status") or "pending"}
            for index, item in enumerate(list_of_maps(payload.get("cancellation_requests")), start=1)
        ],
        key=lambda row: str(row["request_id"]),
    )


def _readiness_rank(readiness: str) -> int:
    return {"blocked": 0, "draining": 1, "unknown": 2, "cancellable": 3}.get(readiness, 4)
