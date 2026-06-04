"""JSON API renderer for insight contradiction resolution status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, mapping, source_metadata, strings

SCHEMA_VERSION = "max.api.insight_contradiction_resolution_status.v1"
KIND = "max.api.insight_contradiction_resolution_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}
RESOLVED_STATES = {"resolved", "closed", "accepted", "dismissed"}


def insight_contradiction_resolution_status_to_json(
    payload: Any,
    *,
    warning_age_hours: float = 24.0,
    critical_age_hours: float = 72.0,
    min_evidence_count: int = 2,
) -> str:
    payload_map = mapping(payload)
    contradictions = _contradictions(payload, warning_age_hours, critical_age_hours, min_evidence_count)
    status = _overall_status(contradictions)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "summary": {
                "contradiction_count": len(contradictions),
                "open_contradiction_count": sum(1 for row in contradictions if row["open"]),
                "critical_contradiction_count": sum(1 for row in contradictions if row["status"] == "critical"),
                "warning_contradiction_count": sum(1 for row in contradictions if row["status"] == "warning"),
                "status": status,
            },
            "contradictions": contradictions,
            "metadata": source_metadata(payload_map, contradiction_count=len(contradictions)),
        },
        indent=2,
        sort_keys=True,
    )


def _contradictions(payload: Any, warning_age_hours: float, critical_age_hours: float, min_evidence_count: int) -> list[dict[str, Any]]:
    payload_map = mapping(payload)
    source = payload_map.get("contradictions") or payload_map.get("items") or (payload if isinstance(payload, list) else [])
    rows = [_contradiction(row, index, warning_age_hours, critical_age_hours, min_evidence_count) for index, row in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["age_hours"], row["contradiction_id"]))


def _contradiction(item: Mapping[str, Any], index: int, warning_age_hours: float, critical_age_hours: float, min_evidence_count: int) -> dict[str, Any]:
    state = _text(item.get("resolution_state") or item.get("state")).lower() or "open"
    is_open = state not in RESOLVED_STATES
    age = max(0.0, float_or_zero(item.get("age_hours")))
    evidence_count = max(0, int_or_zero(item.get("evidence_count")))
    if is_open and age > critical_age_hours:
        status = "critical"
    elif is_open and (age > warning_age_hours or evidence_count < min_evidence_count):
        status = "warning"
    else:
        status = "ok"
    return {
        "contradiction_id": _text(item.get("contradiction_id") or item.get("id")) or f"contradiction-{index}",
        "profile": _text(item.get("profile")) or "default",
        "conflicting_insight_ids": strings(item.get("conflicting_insight_ids")),
        "evidence_count": evidence_count,
        "resolution_state": state,
        "open": is_open,
        "age_hours": age,
        "owner": _text(item.get("owner")) or None,
        "status": status,
    }


def _overall_status(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
