"""JSON API renderer for buildable unit evidence depth status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.buildable_unit_evidence_depth_status.v1"
KIND = "max.api.buildable_unit_evidence_depth_status"
STATUS_RANK = {"blocked": 0, "thin": 1, "ready": 2}


def buildable_unit_evidence_depth_status_to_json(payload: Mapping[str, Any], *, minimum_signal_count: int = 1, minimum_insight_count: int = 1, minimum_source_count: int = 2) -> str:
    rows = [_row(item, index, minimum_signal_count, minimum_insight_count, minimum_source_count) for index, item in enumerate(list_of_maps(payload.get("units") or payload.get("rows") or payload.get("items")), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["unit_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "blocked" if any(row["status"] == "blocked" for row in rows) else "thin" if any(row["status"] == "thin" for row in rows) else "ready", "unit_count": len(rows), "ready_count": sum(1 for row in rows if row["status"] == "ready")}, "units": rows, "metadata": source_metadata(payload, unit_count=len(rows))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, min_signals: int, min_insights: int, min_sources: int) -> dict[str, Any]:
    signals = max(0, int_or_zero(item.get("signal_count", item.get("signals"))))
    insights = max(0, int_or_zero(item.get("insight_count", item.get("insights"))))
    sources = max(0, int_or_zero(item.get("distinct_source_count", item.get("source_count"))))
    missing = []
    if signals < min_signals:
        missing.append("signals")
    if insights < min_insights:
        missing.append("insights")
    if sources < min_sources:
        missing.append("source_diversity")
    status = "ready" if not missing else "blocked" if "signals" in missing or "insights" in missing else "thin"
    return {"unit_id": _text(item.get("unit_id") or item.get("id")) or f"unit-{index}", "profile": _text(item.get("profile")) or "default", "signal_count": signals, "insight_count": insights, "distinct_source_count": sources, "minimum_depth_threshold": {"signal_count": min_signals, "insight_count": min_insights, "distinct_source_count": min_sources}, "missing_depth_reasons": missing, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
