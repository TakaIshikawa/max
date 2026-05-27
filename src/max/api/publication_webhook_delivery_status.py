"""JSON API renderer for publication webhook delivery status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.publication_webhook_delivery_status.v1"
KIND = "max.api.publication_webhook_delivery_status"


def publication_webhook_delivery_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "failing_destinations": [row for row in rows if not row["healthy"]], "metadata": source_metadata(payload, destination_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("destinations") if isinstance(payload.get("destinations"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (row["healthy"], -row["retry_pending_count"], row["destination"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    delivered = max(0, int_or_zero(item.get("delivered_count")))
    failed = max(0, int_or_zero(item.get("failed_count")))
    retry = max(0, int_or_zero(item.get("retry_pending_count")))
    total = delivered + failed
    ratio = round(failed / total, 4) if total else 0.0
    healthy = failed == 0 and retry == 0
    return {"destination": _bucket(item.get("destination"), "unknown_destination"), "endpoint": _text(item.get("endpoint")) or None, "delivered_count": delivered, "failed_count": failed, "retry_pending_count": retry, "last_failure_at": _text(item.get("last_failure_at")) or None, "failure_ratio": ratio, "healthy": healthy, "next_action": "drain retries" if retry else "investigate failures" if failed else "none"}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    delivered = sum(row["delivered_count"] for row in rows)
    failed = sum(row["failed_count"] for row in rows)
    total = delivered + failed
    unhealthy = sum(1 for row in rows if not row["healthy"])
    return {"status": "delivery_failures" if unhealthy else "healthy", "destination_count": len(rows), "failing_count": unhealthy, "delivery_failure_ratio": round(failed / total, 4) if total else 0.0}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
