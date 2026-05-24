"""JSON API renderer for pipeline run artifact inventories."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "max.api.run_artifact_inventory.v1"
KIND = "max.api.run_artifact_inventory"


def run_artifact_inventory_to_json(payload: Mapping[str, Any]) -> str:
    """Render run artifact inventory data as deterministic API JSON."""
    artifacts = _artifacts(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "run_summary": _run_summary(payload),
        "summary": _summary(payload, artifacts),
        "artifacts": artifacts,
        "counts_by_stage": _counts(artifacts, "stage"),
        "counts_by_type": _counts(artifacts, "type"),
        "artifacts_by_stage": _group(artifacts, "stage"),
        "artifacts_by_type": _group(artifacts, "type"),
        "metadata": _metadata(payload, artifacts),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _run_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    run = _mapping(payload.get("run"))
    source = _mapping(payload.get("run_summary"))
    return {
        "run_id": source.get("run_id") or source.get("id") or run.get("id") or payload.get("run_id"),
        "status": source.get("status") or run.get("status"),
        "profile": source.get("profile") or run.get("profile"),
        "domain": source.get("domain") or run.get("domain"),
        "started_at": source.get("started_at") or run.get("started_at"),
        "completed_at": source.get("completed_at") or run.get("completed_at"),
    }


def _summary(payload: Mapping[str, Any], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    explicit = _mapping(payload.get("summary"))
    return {
        "total_artifacts": _int_or_zero(explicit.get("total_artifacts", len(artifacts))),
        "stage_count": _int_or_zero(explicit.get("stage_count", len({row["stage"] for row in artifacts}))),
        "type_count": _int_or_zero(explicit.get("type_count", len({row["type"] for row in artifacts}))),
        "missing_location_count": _int_or_zero(
            explicit.get("missing_location_count", sum(1 for row in artifacts if not row["location"]))
        ),
        "latest_artifact_created_at": explicit.get("latest_artifact_created_at")
        or _max_string(row.get("created_at") for row in artifacts),
    }


def _artifacts(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("artifacts")
    if not isinstance(source, list):
        source = payload.get("artifact_records")
    rows = [
        _artifact_row(item, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(
        rows,
        key=lambda row: (
            str(row["stage"]),
            str(row["type"]),
            str(row["created_at"] or ""),
            str(row["artifact_id"]),
        ),
    )


def _artifact_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    path = item.get("path")
    uri = item.get("uri") or item.get("url")
    location = path or uri
    return {
        "artifact_id": item.get("artifact_id") or item.get("id") or f"artifact-{index}",
        "stage": str(item.get("stage") or "unknown-stage"),
        "type": str(item.get("type") or item.get("artifact_type") or "unknown-type"),
        "path": path,
        "uri": uri,
        "location": location,
        "created_at": item.get("created_at"),
        "metadata": dict(_mapping(item.get("metadata"))),
    }


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row[key]) for row in rows).items()))


def _group(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row[key]), []).append(row)
    return [
        {"name": name, "count": len(items), "artifact_ids": [str(item["artifact_id"]) for item in items]}
        for name, items in sorted(grouped.items())
    ]


def _metadata(payload: Mapping[str, Any], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version") or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "artifact_count": len(artifacts),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _max_string(values: Any) -> str | None:
    candidates = sorted(str(value) for value in values if value)
    return candidates[-1] if candidates else None
