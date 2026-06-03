"""JSON API renderer for source adapter token bucket status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_token_bucket_status.v1"
KIND = "max.api.source_adapter_token_bucket_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def source_adapter_token_bucket_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_remaining_ratio"), 0.15)
    rows = sorted([_row(item, index, warning) for index, item in enumerate(_items(payload), start=1)], key=lambda row: (STATUS_RANK[row["status"]], -row["requests_waiting"], row["source"]))
    summary = _summary(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "adapters": rows, "metadata": source_metadata(payload, adapter_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("adapters") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int, warning: float) -> dict[str, Any]:
    capacity = max(0.0, float_or_zero(item.get("bucket_capacity")))
    remaining = max(0.0, float_or_zero(item.get("tokens_remaining")))
    waiting = max(0, int_or_zero(item.get("requests_waiting")))
    ratio = round(remaining / capacity, 4) if capacity else 0.0
    status = "critical" if remaining <= 0 and waiting > 0 else "warning" if ratio <= warning or waiting > 0 else "ok"
    return {"source": _text(item.get("source")) or f"source-{index}", "bucket_capacity": capacity, "tokens_remaining": remaining, "remaining_ratio": ratio, "refill_rate_per_minute": max(0.0, float_or_zero(item.get("refill_rate_per_minute"))), "requests_waiting": waiting, "next_refill_at": _text(item.get("next_refill_at")), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "adapter_count": len(rows), "constrained_adapter_count": critical + warning, "critical_count": critical, "warning_count": warning, "total_requests_waiting": sum(row["requests_waiting"] for row in rows), "lowest_remaining_ratio": min((row["remaining_ratio"] for row in rows), default=1.0)}


def _float(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
