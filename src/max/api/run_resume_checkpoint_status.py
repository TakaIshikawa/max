"""JSON API renderer for run resume checkpoint status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.run_resume_checkpoint_status.v1"
KIND = "max.api.run_resume_checkpoint_status"
STATUS_RANK = {"failed": 0, "missing_artifact": 1, "resumable": 2, "complete": 3}


def run_resume_checkpoint_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    checkpoints = _checkpoints(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(checkpoints),
        "checkpoints": checkpoints,
        "run_totals": _totals(checkpoints, "run_id"),
        "stage_totals": _totals(checkpoints, "stage"),
        "resume_candidates": [row for row in checkpoints if row["status"] == "resumable"],
        "metadata": _metadata(payload, checkpoints, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _checkpoints(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("checkpoints") if isinstance(payload.get("checkpoints"), list) else payload.get("run_checkpoints")
    rows = [_checkpoint(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["run_id"], row["stage"], row["checkpoint_id"]))
    return rows


def _checkpoint(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    completed_at = item.get("completed_at")
    artifact_uri = _text(item.get("artifact_uri") or item.get("artifact"))
    error = _text(item.get("error") or item.get("error_message"))
    resumable = _bool(item.get("resumable"))
    status = "failed" if error else ("missing_artifact" if completed_at and not artifact_uri else ("resumable" if resumable else ("complete" if completed_at else "resumable")))
    return {
        "run_id": _text(item.get("run_id")) or f"run-{index}",
        "stage": _text(item.get("stage")) or "unknown-stage",
        "checkpoint_id": _text(item.get("checkpoint_id") or item.get("id")) or f"checkpoint-{index}",
        "completed_at": completed_at,
        "artifact_uri": artifact_uri,
        "resumable": resumable,
        "error": error,
        "status": status,
    }


def _summary(checkpoints: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in checkpoints)
    return {"checkpoint_count": len(checkpoints), "resumable_count": counts["resumable"], "failed_count": counts["failed"], "missing_artifact_count": counts["missing_artifact"], "run_count": len({row["run_id"] for row in checkpoints})}


def _totals(checkpoints: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in checkpoints:
        grouped[row[field]].append(row)
    return [{field: key, "checkpoint_count": len(items), "resumable_count": sum(1 for item in items if item["status"] == "resumable"), "failed_count": sum(1 for item in items if item["status"] == "failed")} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], checkpoints: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "checkpoint_count": len(checkpoints)}


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
