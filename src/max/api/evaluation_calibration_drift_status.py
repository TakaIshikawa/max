"""JSON API renderer for evaluation calibration drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.evaluation_calibration_drift_status.v1"
KIND = "max.api.evaluation_calibration_drift_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2, "insufficient_data": 3}


def evaluation_calibration_drift_status_to_json(payload: Mapping[str, Any], *, warning_delta: float = 0.1, critical_delta: float = 0.2) -> str:
    min_samples = max(1, int_or_zero(payload.get("min_sample_count", 1)))
    rows = _rows(payload, warning_delta, critical_delta, min_samples)
    actionable = [row for row in rows if row["status"] != "insufficient_data"]
    worst = max(actionable, key=lambda row: (row["calibration_delta"], row["segment"]), default=None)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_segments": len(rows), "critical_segments": sum(1 for row in rows if row["status"] == "critical"), "warning_segments": sum(1 for row in rows if row["status"] == "warning"), "insufficient_data_segments": sum(1 for row in rows if row["status"] == "insufficient_data"), "worst_segment": worst["segment"] if worst else None}, "segment_rows": rows, "metadata": source_metadata(payload, segment_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warning: float, critical: float, min_samples: int) -> list[dict[str, Any]]:
    source = payload.get("segments") or payload.get("items") or payload
    if isinstance(source, Mapping):
        items = [{**dict(value), "segment": value.get("segment") or key} for key, value in source.items() if isinstance(value, Mapping)]
    elif isinstance(source, list):
        items = [item for item in source if isinstance(item, Mapping)]
    else:
        items = []
    rows = [_row(item, index, warning, critical, min_samples) for index, item in enumerate(items, start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["calibration_delta"], row["segment"]))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float, min_samples: int) -> dict[str, Any]:
    sample_count = max(0, int_or_zero(item.get("sample_count", item.get("samples"))))
    predicted = float_or_zero(item.get("predicted_score", item.get("model_score")))
    observed = float_or_zero(item.get("observed_success_rate", item.get("success_rate")))
    delta = abs(predicted - observed)
    status = "insufficient_data" if sample_count < min_samples else "critical" if delta >= critical else "warning" if delta >= warning else "ok"
    return {"segment": _text(item.get("segment") or item.get("name")) or f"segment-{index}", "sample_count": sample_count, "predicted_score": round(predicted, 4), "observed_success_rate": round(observed, 4), "calibration_delta": round(delta, 4), "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
