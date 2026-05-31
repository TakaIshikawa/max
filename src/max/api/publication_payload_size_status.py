"""JSON API renderer for publication payload size status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publication_payload_size_status.v1"
KIND = "max.api.publication_payload_size_status"


def publication_payload_size_status_to_json(payload: Mapping[str, Any]) -> str:
    default_limit = max(1, int_or_zero(payload.get("limit_bytes") or 1_000_000))
    warning_ratio = float(payload.get("warning_ratio") or 0.8)
    rows = [_row(item, default_limit, warning_ratio) for item in list_of_maps(payload.get("payloads") or payload.get("items"))]
    rows.sort(key=lambda row: (_rank(row["severity"]), -row["payload_bytes"], row["publisher"], row["destination"], row["spec_id"]))
    warning = [row for row in rows if row["severity"] == "warning"]
    blocked = [row for row in rows if row["severity"] == "blocked"]
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "blocked" if blocked else "warning" if warning else "ok", "payload_count": len(rows), "warning_count": len(warning), "blocked_count": len(blocked), "largest_payload_bytes": max((row["payload_bytes"] for row in rows), default=0)}, "rows": rows, "warning_payloads": warning, "blocked_payloads": blocked, "metadata": source_metadata(payload, limit_bytes=default_limit)}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], default_limit: int, warning_ratio: float) -> dict[str, Any]:
    size = _size(item)
    limit = max(1, int_or_zero(item.get("limit_bytes") or item.get("max_bytes") or default_limit))
    utilization = round(size / limit, 4)
    severity = "blocked" if size > limit else "warning" if utilization >= warning_ratio else "ok"
    return {"publisher": _bucket(item.get("publisher") or item.get("target"), "unknown_publisher"), "destination": _bucket(item.get("destination"), "unknown_destination"), "spec_id": str(item.get("spec_id") or item.get("id") or "unknown_spec"), "payload_bytes": size, "limit_bytes": limit, "utilization_ratio": utilization, "severity": severity, "recommended_action": "split_payload" if severity == "blocked" else "trim_payload" if severity == "warning" else "none"}


def _size(item: Mapping[str, Any]) -> int:
    if item.get("payload_bytes") is not None:
        return max(0, int_or_zero(item.get("payload_bytes")))
    if item.get("size_bytes") is not None:
        return max(0, int_or_zero(item.get("size_bytes")))
    serialized = item.get("serialized_payload")
    return len(serialized.encode("utf-8")) if isinstance(serialized, str) else 0


def _rank(value: str) -> int:
    return {"blocked": 0, "warning": 1, "ok": 2}.get(value, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
