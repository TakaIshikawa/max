"""JSON API renderer for run artifact freshness status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, parse_datetime, source_metadata, strings

SCHEMA_VERSION = "max.api.run_artifact_freshness_status.v1"
KIND = "max.api.run_artifact_freshness_status"


def run_artifact_freshness_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    rows = [_row(item, index, payload, as_of) for index, item in enumerate(list_of_maps(payload.get("artifacts") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (not row["stale"], -row["age_minutes"], row["artifact_type"], row["run_id"]))
    required = strings(payload.get("required_artifact_types") or payload.get("required_types"))
    present = {row["artifact_type"] for row in rows}
    missing = [item for item in required if item not in present]
    status = "critical" if missing else ("warning" if any(row["stale"] for row in rows) else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "artifact_count": len(rows), "stale_count": sum(1 for row in rows if row["stale"]), "missing_required_count": len(missing)}, "artifacts": rows, "stale_artifacts": [row for row in rows if row["stale"]], "missing_required_types": missing, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, payload: Mapping[str, Any], as_of: datetime) -> dict[str, Any]:
    artifact_type = str(item.get("artifact_type") or item.get("type") or "unknown_artifact")
    age = float_or_zero(item.get("age_minutes"))
    if "age_minutes" not in item:
        generated = parse_datetime(item.get("generated_at"))
        age = max((as_of - generated).total_seconds() / 60, 0.0) if generated else 0.0
    thresholds = payload.get("freshness_threshold_minutes") if isinstance(payload.get("freshness_threshold_minutes"), Mapping) else {}
    threshold = float_or_zero(item.get("freshness_threshold_minutes", thresholds.get(artifact_type, payload.get("default_freshness_minutes", 60))))
    return {"run_id": str(item.get("run_id") or f"run-{index}"), "artifact_type": artifact_type, "path": str(item.get("path") or ""), "generated_at": item.get("generated_at"), "age_minutes": round(age, 2), "freshness_threshold_minutes": threshold, "stale": age > threshold}
