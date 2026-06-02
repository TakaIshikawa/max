"""JSON API renderer for source adapter retry budget status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_retry_budget_status.v1"
KIND = "max.api.source_adapter_retry_budget_status"


def source_adapter_retry_budget_status_to_json(payload: Mapping[str, Any]) -> str:
    warning_ratio = float_or_zero(payload.get("warning_ratio")) or 0.75
    critical_ratio = float_or_zero(payload.get("critical_ratio")) or 1.0
    rows = [_row(item, warning_ratio, critical_ratio) for item in _items(payload)]
    rows.sort(key=lambda row: (_severity_rank(row["status"]), row["adapter"]))
    summary = _summary(rows)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": summary["status"],
            "summary": summary,
            "totals": summary["totals"],
            "exhausted_count": summary["exhausted_count"],
            "warning_count": summary["warning_count"],
            "adapters": rows,
            "metadata": source_metadata(payload, adapter_count=len(rows)),
        },
        indent=2,
        sort_keys=True,
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("adapters")) or list_of_maps(payload.get("sources")) or list_of_maps(payload.get("items"))


def _row(item: Mapping[str, Any], warning_ratio: float, critical_ratio: float) -> dict[str, Any]:
    adapter = _bucket(item.get("adapter") or item.get("source"), "unknown_adapter")
    source = _bucket(item.get("source") or item.get("adapter"), "unknown_source")
    retries_used = max(0, int_or_zero(item.get("retries_used")))
    retry_budget = max(0, int_or_zero(item.get("retry_budget")))
    failed_attempts = max(0, int_or_zero(item.get("failed_attempts")))
    consumption_ratio = round(retries_used / retry_budget, 4) if retry_budget else (1.0 if retries_used or failed_attempts else 0.0)
    exhausted = retry_budget == 0 and (retries_used > 0 or failed_attempts > 0) or retry_budget > 0 and retries_used >= retry_budget
    status = "critical" if exhausted or consumption_ratio >= critical_ratio else "warning" if consumption_ratio >= warning_ratio else "ok"
    return {
        "adapter": adapter,
        "source": source,
        "retries_used": retries_used,
        "retry_budget": retry_budget,
        "failed_attempts": failed_attempts,
        "remaining_retries": max(retry_budget - retries_used, 0),
        "consumption_ratio": consumption_ratio,
        "exhausted": exhausted,
        "status": status,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exhausted = sum(1 for row in rows if row["exhausted"])
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {
        "status": "critical" if critical else "warning" if warning else "ok",
        "adapter_count": len(rows),
        "exhausted_count": exhausted,
        "warning_count": warning,
        "critical_count": critical,
        "totals": {
            "retries_used": sum(row["retries_used"] for row in rows),
            "retry_budget": sum(row["retry_budget"] for row in rows),
            "failed_attempts": sum(row["failed_attempts"] for row in rows),
        },
    }


def _severity_rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
