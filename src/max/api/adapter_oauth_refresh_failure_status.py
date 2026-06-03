"""JSON API renderer for adapter OAuth refresh failure status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.adapter_oauth_refresh_failure_status.v1"
KIND = "max.api.adapter_oauth_refresh_failure_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def adapter_oauth_refresh_failure_status_to_json(
    payload: Any,
    *,
    failure_rate_warning: float = 0.05,
    failure_rate_critical: float = 0.15,
) -> str:
    rows = _rows(payload, failure_rate_warning, failure_rate_critical)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(rows),
        "adapters": rows,
        "metadata": source_metadata(payload if isinstance(payload, Mapping) else {}, adapter_count=len(rows)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Any, warning: float, critical: float) -> list[dict[str, Any]]:
    source = payload.get("adapters") or payload.get("adapter_metrics") or payload.get("items") or payload if isinstance(payload, Mapping) else payload
    if isinstance(source, Mapping):
        items = [
            {**dict(value), "adapter": value.get("adapter") or key}
            for key, value in source.items()
            if isinstance(value, Mapping)
        ]
    elif isinstance(source, list):
        items = [item for item in source if isinstance(item, Mapping)]
    else:
        items = []
    rows = [_row(item, index, warning, critical) for index, item in enumerate(items, start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["refresh_failures"], -row["failure_rate"], row["adapter"]))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    attempts = max(0, int_or_zero(item.get("refresh_attempts", item.get("attempts"))))
    failures = max(0, int_or_zero(item.get("refresh_failures", item.get("failures"))))
    failure_rate = failures / attempts if attempts else (1.0 if failures else 0.0)
    if failure_rate >= critical or (attempts == 0 and failures > 0):
        status = "critical"
    elif failure_rate >= warning:
        status = "warning"
    else:
        status = "ok"
    return {
        "adapter": _text(item.get("adapter") or item.get("name")) or f"adapter-{index}",
        "refresh_attempts": attempts,
        "refresh_failures": failures,
        "failure_rate": round(failure_rate, 4),
        "status": status,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    highest = rows[0] if rows else None
    return {
        "total_adapters": len(rows),
        "critical_adapters": sum(1 for row in rows if row["status"] == "critical"),
        "warning_adapters": sum(1 for row in rows if row["status"] == "warning"),
        "total_refresh_failures": sum(row["refresh_failures"] for row in rows),
        "highest_failure_adapter": highest["adapter"] if highest else None,
    }


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
