"""JSON API renderer for evidence chain integrity status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, int_or_zero, source_metadata, strings

SCHEMA_VERSION = "max.api.evidence_chain_integrity_status.v1"
KIND = "max.api.evidence_chain_integrity_status"
STATUS_RANK = {"broken": 0, "incomplete": 1, "complete": 2}


def evidence_chain_integrity_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "metadata": source_metadata(payload, checked_units=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("chains") if isinstance(payload.get("chains"), list) else payload.get("items")
    rows = [_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["unit_id"]))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    signals = strings(item.get("signal_ids"))
    missing = strings(item.get("missing_signal_ids"))
    broken_links = strings(item.get("broken_links"))
    required = max(0, int_or_zero(item.get("required_signal_count")))
    status = "broken" if missing or broken_links else ("incomplete" if len(as_list(signals)) < required else "complete")
    return {"unit_id": _text(item.get("unit_id")) or f"unit-{index}", "insight_id": _text(item.get("insight_id")) or None, "signal_ids": signals, "missing_signal_ids": missing, "broken_links": broken_links, "required_signal_count": required, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "broken" if any(row["status"] == "broken" for row in rows) else ("incomplete" if any(row["status"] == "incomplete" for row in rows) else "complete"), "checked_units": len(rows), "broken_units": sum(1 for row in rows if row["status"] == "broken"), "incomplete_units": sum(1 for row in rows if row["status"] == "incomplete"), "missing_signal_total": sum(len(row["missing_signal_ids"]) for row in rows)}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
