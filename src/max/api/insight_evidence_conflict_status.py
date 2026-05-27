"""JSON API renderer for insight evidence conflict status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.insight_evidence_conflict_status.v1"
KIND = "max.api.insight_evidence_conflict_status"


def insight_evidence_conflict_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "unresolved_insights": [row for row in rows if row["unresolved"]], "metadata": source_metadata(payload, insight_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("insights") if isinstance(payload.get("insights"), list) else payload.get("items")
    rows = [_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (not row["unresolved"], -row["conflict_ratio"], row["insight_id"]))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    supporting = max(0, int_or_zero(item.get("supporting_signal_count")))
    contradicting = max(0, int_or_zero(item.get("contradicting_signal_count")))
    conflicts = max(0, int_or_zero(item.get("conflict_count", contradicting)))
    ratio = round(contradicting / (supporting + contradicting), 4) if supporting + contradicting else 0.0
    unresolved = bool(conflicts and not _text(item.get("resolved_at")))
    return {"insight_id": _text(item.get("insight_id")) or f"insight-{index}", "profile": _bucket(item.get("profile"), "default"), "conflict_count": conflicts, "supporting_signal_count": supporting, "contradicting_signal_count": contradicting, "conflict_ratio": ratio, "unresolved": unresolved, "recommended_action": _text(item.get("recommended_action")) or ("review contradictory evidence" if unresolved else "none")}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "conflicts_unresolved" if any(row["unresolved"] for row in rows) else "resolved", "insight_count": len(rows), "total_conflicts": sum(row["conflict_count"] for row in rows), "unresolved_count": sum(1 for row in rows if row["unresolved"]), "highest_conflict_ratio": max((row["conflict_ratio"] for row in rows), default=0.0)}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
