"""JSON API renderer for runtime artifact disk pressure status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.runtime_artifact_disk_pressure_status.v1"
KIND = "max.api.runtime_artifact_disk_pressure_status"


def runtime_artifact_disk_pressure_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _threshold(payload.get("warning_bytes"), 1_000_000_000.0)
    critical = _threshold(payload.get("critical_bytes"), 5_000_000_000.0)
    rows = [_row(item, index) for index, item in enumerate(_items(payload), start=1)]
    total = sum(row["bytes"] for row in rows)
    by_type = Counter()
    for row in rows:
        by_type[row["artifact_type"]] += row["bytes"]
    worst_type, worst_bytes = max(by_type.items(), key=lambda item: (item[1], item[0]), default=(None, 0.0))
    status = "critical" if total >= critical else "warning" if total >= warning else "ok"
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "artifact_count": len(rows),
            "total_bytes": total,
            "max_bytes": critical,
            "worst_artifact_type": worst_type,
            "worst_artifact_type_bytes": worst_bytes,
            "artifacts": rows,
            "metadata": source_metadata(payload, artifact_count=len(rows)),
        },
        indent=2,
        sort_keys=True,
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("artifacts") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "artifact_id": _text(item.get("artifact_id") or item.get("id")) or f"artifact-{index}",
        "artifact_type": _text(item.get("artifact_type") or item.get("type")) or "unknown",
        "bytes": max(0.0, float_or_zero(item.get("bytes") or item.get("size_bytes"))),
    }


def _threshold(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
