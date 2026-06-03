"""JSON API renderer for feedback label drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.feedback_label_drift_status.v1"
KIND = "max.api.feedback_label_drift_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def feedback_label_drift_status_to_json(payload: Mapping[str, Any], *, warning_delta: float = 0.15, critical_delta: float = 0.3) -> str:
    rows = _rows(payload, warning_delta, critical_delta)
    largest = max(rows, key=lambda row: (row["share_delta"], row["label"]), default=None)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_labels": len(rows), "drifting_labels": sum(1 for row in rows if row["status"] != "ok"), "critical_labels": sum(1 for row in rows if row["status"] == "critical"), "largest_drift_label": largest["label"] if largest else None}, "label_rows": rows, "metadata": source_metadata(payload, label_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warning: float, critical: float) -> list[dict[str, Any]]:
    current = {str(key): max(0, int_or_zero(value)) for key, value in (payload.get("current_counts") or {}).items()} if isinstance(payload.get("current_counts"), Mapping) else {}
    baseline = {str(key): max(0, int_or_zero(value)) for key, value in (payload.get("baseline_counts") or {}).items()} if isinstance(payload.get("baseline_counts"), Mapping) else {}
    current_total = sum(current.values())
    baseline_total = sum(baseline.values())
    rows = []
    for label in sorted(set(current) | set(baseline)):
        current_share = current.get(label, 0) / current_total if current_total else 0.0
        baseline_share = baseline.get(label, 0) / baseline_total if baseline_total else 0.0
        delta = abs(current_share - baseline_share)
        status = "critical" if delta >= critical else "warning" if delta >= warning else "ok"
        rows.append({"label": label, "current_count": current.get(label, 0), "baseline_count": baseline.get(label, 0), "current_share": round(current_share, 4), "baseline_share": round(baseline_share, 4), "share_delta": round(delta, 4), "status": status})
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["share_delta"], row["label"]))
