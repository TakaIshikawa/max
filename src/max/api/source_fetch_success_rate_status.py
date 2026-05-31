"""JSON API renderer for source fetch success rate status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.source_fetch_success_rate_status.v1"
KIND = "max.api.source_fetch_success_rate_status"


def source_fetch_success_rate_status_to_json(
    payload: Mapping[str, Any],
    *,
    warning_threshold: float | None = None,
    critical_threshold: float | None = None,
) -> str:
    warn = _ratio(warning_threshold if warning_threshold is not None else payload.get("warning_threshold"), 0.9)
    critical = _ratio(critical_threshold if critical_threshold is not None else payload.get("critical_threshold"), 0.75)
    rows = _rows(payload, warn, critical)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(rows, warn, critical),
        "rows": rows,
        "metadata": source_metadata(payload, source_count=len(rows)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warn: float, critical: float) -> list[dict[str, Any]]:
    source = payload.get("sources") if isinstance(payload.get("sources"), list) else payload.get("fetches")
    items = [item for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    grouped: dict[str, dict[str, int]] = {}
    for item in items:
        name = _text(item.get("source") or item.get("source_name") or item.get("name") or "unknown_source")
        bucket = grouped.setdefault(name, {"attempts": 0, "successes": 0, "failures": 0, "recent_error_count": 0})
        attempts = max(0, int_or_zero(item.get("attempts", item.get("attempt_count"))))
        successes = max(0, int_or_zero(item.get("successes", item.get("success_count"))))
        failures = max(0, int_or_zero(item.get("failures", item.get("failure_count"))))
        if attempts == 0 and any(key in item for key in ("status", "success", "ok")):
            attempts = 1
            successes = 1 if _success(item) else 0
            failures = 0 if successes else 1
        if attempts == 0 and (successes or failures):
            attempts = successes + failures
        bucket["attempts"] += attempts
        bucket["successes"] += successes
        bucket["failures"] += failures
        bucket["recent_error_count"] += max(0, int_or_zero(item.get("recent_error_count", item.get("recent_errors"))))
    rows = [_row(source, counts, warn, critical) for source, counts in grouped.items()]
    return sorted(rows, key=lambda row: (row["severity_rank"], row["source"]))


def _row(source: str, counts: Mapping[str, int], warn: float, critical: float) -> dict[str, Any]:
    attempts = counts["attempts"]
    successes = min(counts["successes"], attempts) if attempts else counts["successes"]
    failures = max(counts["failures"], attempts - successes) if attempts else counts["failures"]
    success_rate = round(successes / attempts, 4) if attempts else None
    severity = "unknown" if attempts == 0 else "critical" if success_rate < critical else "warn" if success_rate < warn else "healthy"
    return {
        "source": source,
        "attempts": attempts,
        "successes": successes,
        "failures": failures,
        "success_rate": success_rate,
        "recent_error_count": counts["recent_error_count"],
        "severity": severity,
        "severity_rank": {"critical": 0, "warn": 1, "unknown": 2, "healthy": 3}[severity],
    }


def _summary(rows: list[dict[str, Any]], warn: float, critical: float) -> dict[str, Any]:
    attempts = sum(row["attempts"] for row in rows)
    successes = sum(row["successes"] for row in rows)
    return {
        "source_count": len(rows),
        "total_attempts": attempts,
        "total_successes": successes,
        "total_failures": sum(row["failures"] for row in rows),
        "overall_success_rate": round(successes / attempts, 4) if attempts else None,
        "warning_threshold": warn,
        "critical_threshold": critical,
        "critical_count": sum(1 for row in rows if row["severity"] == "critical"),
        "warning_count": sum(1 for row in rows if row["severity"] == "warn"),
        "unknown_count": sum(1 for row in rows if row["severity"] == "unknown"),
    }


def _success(item: Mapping[str, Any]) -> bool:
    value = item.get("success", item.get("ok", item.get("status")))
    return str(value).strip().lower() in {"1", "true", "yes", "ok", "success", "succeeded"}


def _ratio(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if number > 1:
        number /= 100
    return round(min(max(number, 0.0), 1.0), 4)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) or "unknown_source"
