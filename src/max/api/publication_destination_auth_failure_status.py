"""JSON API renderer for publication destination auth failure status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.publication_destination_auth_failure_status.v1"
KIND = "max.api.publication_destination_auth_failure_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def publication_destination_auth_failure_status_to_json(payload: Mapping[str, Any], *, warning_failures: int = 1, critical_failures: int = 3) -> str:
    rows = _rows(payload, warning_failures, critical_failures)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_destinations": len(rows), "critical_destinations": sum(1 for row in rows if row["status"] == "critical"), "warning_destinations": sum(1 for row in rows if row["status"] == "warning"), "total_auth_failures": sum(row["auth_failures"] for row in rows)}, "destination_rows": rows, "metadata": source_metadata(payload, destination_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warning: int, critical: int) -> list[dict[str, Any]]:
    source = payload.get("destinations") or payload.get("items") or payload
    if isinstance(source, Mapping):
        items = [{**dict(value), "destination": value.get("destination") or key} for key, value in source.items() if isinstance(value, Mapping)]
    elif isinstance(source, list):
        items = [item for item in source if isinstance(item, Mapping)]
    else:
        items = []
    rows = [_row(item, index, warning, critical) for index, item in enumerate(items, start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["auth_failures"], row["destination"]))


def _row(item: Mapping[str, Any], index: int, warning: int, critical: int) -> dict[str, Any]:
    failures = max(0, int_or_zero(item.get("recent_auth_failures", item.get("auth_failures"))))
    status = "critical" if failures >= critical else "warning" if failures >= warning else "ok"
    if bool(item.get("successful_recent_check")) and failures == 0:
        status = "ok"
    return {"destination": _text(item.get("destination") or item.get("name")) or f"destination-{index}", "auth_failures": failures, "last_failure_at": item.get("last_failure_at"), "remediation_hint": _text(item.get("remediation_hint")) or None, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
