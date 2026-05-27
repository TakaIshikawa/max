"""JSON API renderer for feedback label quality status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.feedback_label_quality_status.v1"
KIND = "max.api.feedback_label_quality_status"
STATUS_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def feedback_label_quality_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    labelers = _labelers(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(labelers), "labelers": labelers, "status_totals": _status_totals(labelers), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, labeler_count=len(labelers))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _labelers(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("labelers") if isinstance(payload.get("labelers"), list) else payload.get("label_quality")
    rows = [_labeler(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["disagreement_rate"], row["labeler"], row["profile"]))


def _labeler(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    reviewed = max(0, int_or_zero(item.get("reviewed_count", item.get("reviewed"))))
    disagreement = max(0, int_or_zero(item.get("disagreement_count", item.get("disagreements"))))
    rate = _rate(item.get("disagreement_rate"), disagreement, reviewed)
    calibration = _clamp(item.get("calibration_score", item.get("calibration")))
    status = _status(item.get("status"), rate, calibration)
    return {"labeler": _text(item.get("labeler")) or f"labeler-{index}", "profile": _bucket(item.get("profile"), "default"), "reviewed_count": reviewed, "disagreement_count": disagreement, "disagreement_rate": rate, "calibration_score": calibration, "status": status}


def _rate(value: Any, disagreement: int, reviewed: int) -> float:
    raw = float_or_zero(value) if value is not None else (disagreement / reviewed if reviewed else 0.0)
    return _clamp(raw)


def _clamp(value: Any) -> float:
    return round(min(max(float_or_zero(value), 0.0), 1.0), 4)


def _status(value: Any, rate: float, calibration: float) -> str:
    explicit = _bucket(value, "")
    if explicit in STATUS_RANK:
        return explicit
    if rate >= 0.4 or (calibration and calibration < 0.5):
        return "critical"
    if rate >= 0.25 or (calibration and calibration < 0.7):
        return "high"
    if rate >= 0.1 or (calibration and calibration < 0.85):
        return "medium"
    return "low"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    average = round(sum(row["disagreement_rate"] for row in rows) / len(rows), 4) if rows else 0.0
    return {"status": "critical" if counts["critical"] else ("high" if counts["high"] else ("medium" if counts["medium"] else "low")), "labeler_count": len(rows), "low_quality_count": sum(1 for row in rows if row["status"] in {"critical", "high"}), "average_disagreement_rate": average}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "labeler_count": counts[status]} for status in ("critical", "high", "medium", "low")]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
