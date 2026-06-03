"""JSON API renderer for run artifact storage pressure status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.run_artifact_storage_pressure_status.v1"
KIND = "max.api.run_artifact_storage_pressure_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def run_artifact_storage_pressure_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _threshold(payload.get("warning_usage_ratio"), 0.75)
    critical = _threshold(payload.get("critical_usage_ratio"), 0.9)
    rows = sorted(
        [_row(item, index, warning, critical) for index, item in enumerate(_items(payload), start=1)],
        key=lambda row: (STATUS_RANK[row["status"]], -row["usage_ratio"], row["artifact_type"]),
    )
    critical_count = sum(1 for row in rows if row["status"] == "critical")
    warning_count = sum(1 for row in rows if row["status"] == "warning")
    status = "critical" if critical_count else "warning" if warning_count else "ok"
    summary = {
        "artifact_type_count": len(rows),
        "pressured_artifact_type_count": critical_count + warning_count,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "max_usage_ratio": max((row["usage_ratio"] for row in rows), default=0.0),
    }
    return json.dumps(
        {"schema_version": SCHEMA_VERSION, "kind": KIND, "status": status, "summary": summary, "artifacts": rows, "metadata": source_metadata(payload, artifact_type_count=len(rows))},
        indent=2,
        sort_keys=True,
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("artifacts") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    used = max(0.0, float_or_zero(item.get("bytes_used")))
    limit = max(0.0, float_or_zero(item.get("byte_limit")))
    ratio = round(used / limit, 4) if limit > 0 else 0.0
    retention = max(0.0, float_or_zero(item.get("retention_days")))
    oldest = max(0.0, float_or_zero(item.get("oldest_artifact_age_days")))
    status, reason = _classify(used, limit, ratio, oldest, retention, warning, critical)
    return {
        "artifact_type": _text(item.get("artifact_type") or item.get("type")) or f"artifact-{index}",
        "bytes_used": used,
        "byte_limit": limit,
        "usage_ratio": ratio,
        "retention_days": retention,
        "oldest_artifact_age_days": oldest,
        "status": status,
        "reason": reason,
    }


def _classify(used: float, limit: float, ratio: float, oldest: float, retention: float, warning: float, critical: float) -> tuple[str, str]:
    if limit <= 0 and used > 0:
        return "critical", "missing_byte_limit"
    if retention > 0 and oldest > retention:
        return "critical", "retention_age_breach"
    if ratio >= critical:
        return "critical", "critical_usage"
    if ratio >= warning:
        return "warning", "warning_usage"
    return "ok", "within_policy"


def _threshold(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
