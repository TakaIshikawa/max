"""JSON API renderer for evaluation calibration status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.evaluation_calibration_status.v1"
KIND = "max.api.evaluation_calibration_status"
STATUS_RANK = {"recalibrate": 0, "monitor": 1, "insufficient_data": 2, "stable": 3}


def evaluation_calibration_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    calibrations = _calibrations(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(calibrations),
        "calibrations": calibrations,
        "recalibration_candidates": [row for row in calibrations if row["status"] == "recalibrate"],
        "profile_totals": _totals(calibrations, "profile"),
        "dimension_totals": _totals(calibrations, "dimension"),
        "metadata": _metadata(payload, calibrations, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _calibrations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("calibrations") if isinstance(payload.get("calibrations"), list) else payload.get("weights")
    rows = [_calibration(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["dimension"]))
    return rows


def _calibration(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    current = _score(item.get("current_weight", item.get("current")))
    recommended = _score(item.get("recommended_weight", item.get("recommended")))
    delta = _float(item.get("delta")) if item.get("delta") is not None else round(recommended - current, 4)
    sample_size = _int(item.get("sample_size", item.get("samples")))
    confidence = _score(item.get("confidence"))
    status = _status(delta, sample_size, confidence)
    return {
        "profile": _text(item.get("profile")) or "unknown-profile",
        "dimension": _text(item.get("dimension")) or f"dimension-{index}",
        "current_weight": current,
        "recommended_weight": recommended,
        "delta": delta,
        "sample_size": sample_size,
        "confidence": confidence,
        "status": status,
    }


def _status(delta: float, sample_size: int, confidence: float) -> str:
    if sample_size < 30:
        return "insufficient_data"
    if abs(delta) >= 0.15 and confidence >= 0.7:
        return "recalibrate"
    if abs(delta) >= 0.05 or confidence < 0.7:
        return "monitor"
    return "stable"


def _summary(calibrations: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in calibrations)
    return {"calibration_count": len(calibrations), "stable_count": counts["stable"], "monitor_count": counts["monitor"], "recalibrate_count": counts["recalibrate"], "insufficient_data_count": counts["insufficient_data"]}


def _totals(calibrations: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in calibrations:
        grouped[row[field]].append(row)
    return [{field: key, "calibration_count": len(items), "recalibrate_count": sum(1 for item in items if item["status"] == "recalibrate")} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], calibrations: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "calibration_count": len(calibrations)}


def _score(value: Any) -> float:
    try:
        return round(min(max(float(value or 0), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _float(value: Any) -> float:
    try:
        return round(float(value or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
