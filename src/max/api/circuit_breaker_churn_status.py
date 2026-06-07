"""JSON API renderer for source adapter circuit-breaker churn status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.circuit_breaker_churn_status.v1"
KIND = "max.api.circuit_breaker_churn_status"


def circuit_breaker_churn_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _threshold(payload.get("warning_churn_threshold"), 3.0)
    critical = _threshold(payload.get("critical_churn_threshold"), 6.0)
    rows = [_row(item, index) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (-row["churn_score"], row["adapter"]))
    opened_count = sum(row["opened_count"] for row in rows)
    reopen_count = sum(row["reopen_count"] for row in rows)
    churn_score = round(opened_count + (reopen_count * 2), 4)
    status = "critical" if churn_score >= critical else "warning" if churn_score >= warning else "ok"
    worst_adapter = rows[0]["adapter"] if rows else None
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "adapter_count": len(rows),
            "worst_adapter": worst_adapter,
            "opened_count": opened_count,
            "reopen_count": reopen_count,
            "churn_score": churn_score,
            "adapters": rows,
            "metadata": source_metadata(payload, adapter_count=len(rows)),
        },
        indent=2,
        sort_keys=True,
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("adapters") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    opened = max(0, int_or_zero(item.get("opened_count") or item.get("open_count")))
    reopened = max(0, int_or_zero(item.get("reopen_count") or item.get("reopened_count")))
    return {
        "adapter": _text(item.get("adapter") or item.get("source")) or f"adapter-{index}",
        "opened_count": opened,
        "reopen_count": reopened,
        "churn_score": round(opened + (reopened * 2), 4),
    }


def _threshold(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
