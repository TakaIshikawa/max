"""JSON API renderer for source adapter schema compatibility status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_schema_compatibility_status.v1"
KIND = "max.api.source_adapter_schema_compatibility_status"
STATUS_RANK = {"incompatible": 0, "degraded": 1, "compatible": 2}


def source_adapter_schema_compatibility_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item) for item in list_of_maps(payload.get("adapters") or payload.get("rows") or payload.get("items"))]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["adapter"], row["schema_version"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "incompatible" if any(row["status"] == "incompatible" for row in rows) else "degraded" if any(row["status"] == "degraded" for row in rows) else "compatible", "adapter_count": len(rows), "incompatible_count": sum(1 for row in rows if row["status"] == "incompatible")}, "adapters": rows, "metadata": source_metadata(payload, adapter_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    unsupported = _strings(item.get("unsupported_fields"))
    missing = _strings(item.get("missing_required_fields"))
    decision = _text(item.get("compatibility_decision") or item.get("decision")).lower()
    status = "incompatible" if missing or decision == "incompatible" else "degraded" if unsupported or decision == "degraded" else "compatible"
    return {"adapter": _text(item.get("adapter") or item.get("adapter_id")) or "unknown", "schema_version": _text(item.get("schema_version")) or "unknown", "unsupported_fields": unsupported, "missing_required_fields": missing, "compatibility_decision": status, "status": status}


def _strings(value: Any) -> list[str]:
    return [_text(item) for item in as_list(value) if _text(item)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
