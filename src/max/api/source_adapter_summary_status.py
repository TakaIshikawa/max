"""JSON API renderer for source adapter summary status."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from max.api._renderer_utils import bool_or_default, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_summary_status.v1"
KIND = "max.api.source_adapter_summary_status"
STATUS_RANK = {"error": 0, "warning": 1, "healthy": 2, "idle": 3}


def source_adapter_summary_status_to_json(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> str:
    rows = [_row(item) for item in _items(payload)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["adapter"], row["profile"]))
    metadata = source_metadata(payload if isinstance(payload, Mapping) else {}, adapter_count=len(rows))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "adapters": rows, "metadata": metadata}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    fetched = max(0, int_or_zero(item.get("fetched_count", item.get("fetched"))))
    failed = max(0, int_or_zero(item.get("failed_count", item.get("failed"))))
    warning = bool_or_default(item.get("warning"), default=False)
    status = "idle" if fetched == 0 and failed == 0 else "error" if failed else "warning" if warning else "healthy"
    return {"adapter": _text(item.get("adapter")) or "unknown", "profile": _text(item.get("profile")) or "default", "fetched_count": fetched, "failed_count": failed, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "error" if any(row["status"] == "error" for row in rows) else "warning" if any(row["status"] == "warning" for row in rows) else "healthy" if any(row["status"] == "healthy" for row in rows) else "idle", "adapter_count": len(rows), "fetched_count": sum(row["fetched_count"] for row in rows), "failed_count": sum(row["failed_count"] for row in rows)}


def _items(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return list_of_maps(payload.get("adapters") or payload.get("rows") or payload.get("items"))
    return [item for item in payload if isinstance(item, Mapping)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
