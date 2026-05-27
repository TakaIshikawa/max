"""JSON API renderer for signal freshness regression status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.signal_freshness_regression_status.v1"
KIND = "max.api.signal_freshness_regression_status"


def signal_freshness_regression_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "regressed_signals": [row for row in rows if row["status"] == "regressed"], "metadata": source_metadata(payload, signal_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    threshold = max(0.0, float_or_zero(payload.get("regression_threshold_hours") or 24))
    source = payload.get("signals") if isinstance(payload.get("signals"), list) else payload.get("items")
    rows = [_row(item, threshold) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (row["status"] != "regressed", -row["freshness_delta_hours"], row["source"], row["profile"]))


def _row(item: Mapping[str, Any], threshold: float) -> dict[str, Any]:
    current = round(max(0.0, float_or_zero(item.get("current_age_hours"))), 4)
    baseline_raw = item.get("baseline_age_hours")
    baseline_known = baseline_raw not in (None, "")
    baseline = round(max(0.0, float_or_zero(baseline_raw)), 4) if baseline_known else None
    delta = round(current - (baseline or 0.0), 4) if baseline_known else 0.0
    status = "insufficient_baseline" if not baseline_known else "regressed" if delta > threshold else "stable"
    return {"source": _bucket(item.get("source"), "unknown_source"), "profile": _bucket(item.get("profile"), "unknown_profile"), "current_age_hours": current, "baseline_age_hours": baseline, "freshness_delta_hours": delta, "stale_signal_count": max(0, int_or_zero(item.get("stale_signal_count"))), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    regressed = sum(1 for row in rows if row["status"] == "regressed")
    unknown = sum(1 for row in rows if row["status"] == "insufficient_baseline")
    return {"status": "regressed" if regressed else "insufficient_baseline" if unknown else "stable", "signal_count": len(rows), "regressed_count": regressed, "insufficient_baseline_count": unknown, "stale_signal_count": sum(row["stale_signal_count"] for row in rows)}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
