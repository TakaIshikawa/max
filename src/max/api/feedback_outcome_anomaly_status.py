"""JSON API renderer for feedback outcome anomaly status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.feedback_outcome_anomaly_status.v1"
KIND = "max.api.feedback_outcome_anomaly_status"
STATUS_RANK = {"critical": 0, "warning": 1, "insufficient_data": 2, "ok": 3}


def feedback_outcome_anomaly_status_to_json(payload: Mapping[str, Any], *, warning_delta: float = 0.15, critical_delta: float = 0.3, minimum_sample_size: int = 10) -> str:
    rows = [_row(item, index, warning_delta, critical_delta, minimum_sample_size) for index, item in enumerate(_items(payload), start=1)]
    rows = sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["approval_rate_delta"], row["segment"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"segment_count": len(rows), "anomalous_segments": sum(1 for row in rows if row["status"] in {"warning", "critical"}), "critical_segments": sum(1 for row in rows if row["status"] == "critical")}, "segment_rows": rows, "metadata": source_metadata(payload, segment_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("segments") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float, minimum: int) -> dict[str, Any]:
    approved = _non_negative(item.get("approved_count"))
    rejected = _non_negative(item.get("rejected_count"))
    neutral = _non_negative(item.get("neutral_count"))
    sample = approved + rejected + neutral
    approval = approved / sample if sample else 0.0
    baseline = min(max(_float(item.get("baseline_approval_rate")), 0.0), 1.0)
    delta = abs(approval - baseline)
    status = "insufficient_data" if sample < minimum else "critical" if delta >= critical else "warning" if delta >= warning else "ok"
    segment = _text(item.get("segment") or item.get("profile") or item.get("reviewer")) or f"segment-{index}"
    return {"segment": segment, "profile": _text(item.get("profile")) or None, "reviewer": _text(item.get("reviewer")) or None, "sample_count": sample, "approval_rate": round(approval, 4), "baseline_approval_rate": round(baseline, 4), "approval_rate_delta": round(delta, 4), "approved_count": approved, "rejected_count": rejected, "neutral_count": neutral, "status": status}


def _non_negative(value: Any) -> int:
    return max(0, int_or_zero(value))


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
