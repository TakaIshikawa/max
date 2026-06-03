"""JSON API renderer for source adapter content hash churn status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_content_hash_churn_status.v1"
KIND = "max.api.source_adapter_content_hash_churn_status"


def source_adapter_content_hash_churn_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_churn_rate"), 0.2)
    critical = _float(payload.get("critical_churn_rate"), 0.5)
    adapters = [_adapter(row, warning, critical) for row in _items(payload)]
    adapters.sort(key=lambda row: (_rank(row["status"]), row["source"]))
    summary = _summary(adapters)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "adapters": adapters, "metadata": source_metadata(payload, adapter_count=len(adapters))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("adapters")) or list_of_maps(payload.get("items")) or list_of_maps(payload.get("rows"))


def _adapter(row: Mapping[str, Any], warning: float, critical: float) -> dict[str, Any]:
    changes = max(0, int_or_zero(row.get("hash_changes")))
    fetched = max(0, int_or_zero(row.get("fetched_count")))
    rate = round(changes / fetched, 4) if fetched else 0.0
    status = "critical" if rate >= critical else "warning" if rate >= warning else "ok"
    return {"source": _bucket(row.get("source") or row.get("adapter"), "unknown_source"), "hash_changes": changes, "fetched_count": fetched, "window_hours": max(0, int_or_zero(row.get("window_hours"))), "churn_rate": rate, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "adapter_count": len(rows), "noisy_adapter_count": critical + warning, "critical_count": critical, "warning_count": warning}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
