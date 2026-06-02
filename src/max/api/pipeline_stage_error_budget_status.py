"""JSON API renderer for pipeline stage error budget status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.pipeline_stage_error_budget_status.v1"
KIND = "max.api.pipeline_stage_error_budget_status"


def pipeline_stage_error_budget_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(row) for row in _items(payload)]
    rows.sort(key=lambda row: (_rank(row["status"]), -row["failure_rate"], row["stage"]))
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": "critical" if critical else "warning" if warning else "ok", "summary": {"stage_count": len(rows), "critical_count": critical, "warning_count": warning}, "stages": rows, "metadata": source_metadata(payload, stage_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("stages")) or list_of_maps(payload.get("items"))


def _row(row: Mapping[str, Any]) -> dict[str, Any]:
    failures = max(0, int_or_zero(row.get("failures")))
    total = max(0, int_or_zero(row.get("total_runs")))
    allowed = max(0.0, float_or_zero(row.get("allowed_failure_rate")))
    recent = max(0, int_or_zero(row.get("recent_failures")))
    failure_rate = round(failures / total, 4) if total else 0.0
    remaining = round(max(allowed - failure_rate, 0) / allowed, 4) if allowed else (0.0 if failures else 1.0)
    status = "critical" if (total and failure_rate > allowed) or (allowed == 0 and failures) else "warning" if recent else "ok"
    return {"stage": _bucket(row.get("stage"), "unknown_stage"), "failures": failures, "total_runs": total, "allowed_failure_rate": allowed, "recent_failures": recent, "failure_rate": failure_rate, "remaining_budget_ratio": remaining, "status": status}


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
