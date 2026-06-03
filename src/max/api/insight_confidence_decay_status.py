"""JSON API renderer for insight confidence decay status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.insight_confidence_decay_status.v1"
KIND = "max.api.insight_confidence_decay_status"


def insight_confidence_decay_status_to_json(payload: Mapping[str, Any]) -> str:
    minimum = _float(payload.get("minimum_confidence"), 0.5)
    warning_decay = _float(payload.get("warning_decay"), 0.2)
    critical_decay = _float(payload.get("critical_decay"), 0.4)
    insights = [_insight(row, minimum, warning_decay, critical_decay) for row in _items(payload)]
    insights.sort(key=lambda row: (_rank(row["status"]), row["profile"], row["insight_id"]))
    summary = _summary(insights)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "insights": insights, "metadata": source_metadata(payload, insight_count=len(insights))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("insights")) or list_of_maps(payload.get("items")) or list_of_maps(payload.get("rows"))


def _insight(row: Mapping[str, Any], minimum: float, warning_decay: float, critical_decay: float) -> dict[str, Any]:
    confidence = max(0.0, float_or_zero(row.get("confidence")))
    original = max(0.0, float_or_zero(row.get("original_confidence")))
    delta = round(confidence - original, 4)
    decay = max(0.0, original - confidence)
    status = "critical" if confidence < minimum or decay >= critical_decay else "warning" if decay >= warning_decay else "ok"
    return {"insight_id": _bucket(row.get("insight_id") or row.get("id"), "unknown_insight"), "profile": _bucket(row.get("profile"), "unknown_profile"), "confidence": confidence, "original_confidence": original, "confidence_delta": delta, "age_days": max(0, int_or_zero(row.get("age_days"))), "evidence_refresh_count": max(0, int_or_zero(row.get("evidence_refresh_count"))), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "total": len(rows), "refresh_candidate_count": critical + warning, "critical_count": critical, "warning_count": warning}


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
