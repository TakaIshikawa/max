"""JSON API renderer for source adapter pagination cursor status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_pagination_cursor_status.v1"
KIND = "max.api.source_adapter_pagination_cursor_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def source_adapter_pagination_cursor_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item, index) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (RANK[row["status"]], row["adapter"], row["source"]))
    affected = [row for row in rows if row["status"] != "healthy"]
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if affected else "healthy"), "cursor_count": len(rows), "affected_adapter_count": len(affected)}, "cursor_summaries": rows, "affected_adapters": affected, "actions": _actions(affected), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = list_of_maps(payload.get("cursors") or payload.get("rows"))
    for adapter in list_of_maps(payload.get("adapters")):
        for cursor in list_of_maps(adapter.get("sources") or adapter.get("cursors")):
            rows.append({**cursor, "adapter": cursor.get("adapter") or adapter.get("adapter") or adapter.get("adapter_id")})
    return rows


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    duplicate = int_or_zero(item.get("duplicate_page_count"))
    empty = int_or_zero(item.get("empty_page_count"))
    lag = int_or_zero(item.get("lag_seconds"))
    stale_after = int_or_zero(item.get("stale_after_seconds") or 3600)
    reset = bool(item.get("reset_required"))
    status = "critical" if reset or duplicate >= 3 else ("warning" if empty >= 3 or lag > stale_after else "healthy")
    return {"adapter": str(item.get("adapter") or item.get("adapter_id") or f"adapter-{index}"), "source": str(item.get("source") or item.get("source_id") or "unknown"), "cursor": item.get("cursor"), "cursor_updated_at": item.get("cursor_updated_at"), "lag_seconds": lag, "page_size": int_or_zero(item.get("page_size")), "empty_page_count": empty, "duplicate_page_count": duplicate, "reset_required": reset, "status": status, "action": _action(status)}


def _action(status: str) -> str:
    return {"critical": "reset the pagination cursor and inspect duplicate page loops", "warning": "refresh stale cursors or reduce repeated empty page scans"}.get(status, "none")


def _actions(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({_action(row["status"]) for row in rows if row["status"] != "healthy"})
