"""JSON API renderer for evaluation score outlier status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.evaluation_score_outlier_status.v1"
KIND = "max.api.evaluation_score_outlier_status"
DEFAULT_Z_THRESHOLD = 2.0


def evaluation_score_outlier_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "outlier_evaluations": [row for row in rows if row["outlier"]], "metadata": source_metadata(payload, evaluation_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    threshold = max(0.0, float_or_zero(payload.get("z_score_threshold") or DEFAULT_Z_THRESHOLD))
    source = payload.get("evaluations") if isinstance(payload.get("evaluations"), list) else payload.get("items")
    rows = [_row(item, threshold, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (not row["outlier"], -abs(row["deviation"]), row["unit_id"]))


def _row(item: Mapping[str, Any], threshold: float, index: int) -> dict[str, Any]:
    score = round(float_or_zero(item.get("score")), 4)
    median = round(float_or_zero(item.get("median_score")), 4)
    raw_z = item.get("z_score")
    deviation = round(float_or_zero(raw_z if raw_z is not None else score - median), 4)
    outlier = abs(deviation) >= threshold
    direction = "high" if deviation > 0 else "low" if deviation < 0 else "none"
    return {"unit_id": _text(item.get("unit_id")) or f"unit-{index}", "profile": _bucket(item.get("profile"), "unknown_profile"), "score": score, "median_score": median, "deviation": deviation, "outlier_direction": direction if outlier else "none", "outlier": outlier, "review_recommendation": f"review_{direction}_score" if outlier else "none"}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    outlier_count = sum(1 for row in rows if row["outlier"])
    return {"status": "review_required" if outlier_count else "normal", "evaluation_count": len(rows), "outlier_count": outlier_count, "high_outlier_count": sum(1 for row in rows if row["outlier_direction"] == "high"), "low_outlier_count": sum(1 for row in rows if row["outlier_direction"] == "low")}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
