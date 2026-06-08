"""Adapter health rollup export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.adapter_health_rollup_report.v1"
KIND = "max.adapter_health_rollup_report"

_SUCCESS_STATUSES = {"success", "succeeded", "ok", "ready", "complete", "completed", "passed"}
_TIMEOUT_STATUSES = {"timeout", "timed out", "timed_out"}
_FAILURE_STATUSES = {"failure", "failed", "error", "errored", "cancelled", "canceled"}
_STATUS_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def generate_adapter_health_rollup_report(
    records: Iterable[dict[str, Any]],
    *,
    warning_success_rate: float = 0.95,
    critical_success_rate: float = 0.8,
) -> dict[str, Any]:
    warning = _ratio(warning_success_rate)
    critical = _ratio(critical_success_rate)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        adapter = _text(raw.get("adapter") or raw.get("adapter_name") or raw.get("name") or raw.get("id")) or "unknown-adapter"
        source = _text(raw.get("source") or raw.get("source_name") or raw.get("source_id")) or "unknown-source"
        group = groups.setdefault((adapter, source), {"success": 0, "failure": 0, "timeout": 0, "latest": ""})
        group["success"] += _int(raw.get("success_count") or raw.get("successes"))
        group["failure"] += _int(raw.get("failure_count") or raw.get("failures") or raw.get("error_count") or raw.get("errors"))
        group["timeout"] += _int(raw.get("timeout_count") or raw.get("timeouts"))
        if not any(raw.get(key) is not None for key in ("success_count", "successes", "failure_count", "failures", "error_count", "errors", "timeout_count", "timeouts")):
            status = _status(raw)
            if status in _SUCCESS_STATUSES:
                group["success"] += 1
            elif status in _TIMEOUT_STATUSES:
                group["timeout"] += 1
            else:
                group["failure"] += 1
        seen_at = _text(raw.get("seen_at") or raw.get("latest_seen_at") or raw.get("finished_at") or raw.get("completed_at") or raw.get("timestamp") or raw.get("created_at"))
        if seen_at > group["latest"]:
            group["latest"] = seen_at

    rows = []
    for (adapter, source), group in groups.items():
        total = group["success"] + group["failure"] + group["timeout"]
        success_rate = round(group["success"] / total, 4) if total else 0.0
        rows.append(
            {
                "adapter": adapter,
                "source": source,
                "success_count": group["success"],
                "failure_count": group["failure"],
                "timeout_count": group["timeout"],
                "total_count": total,
                "success_rate": success_rate,
                "latest_seen_at": group["latest"] or None,
                "status": _rollup_status(success_rate, warning, critical),
            }
        )
    rows.sort(key=lambda row: (_STATUS_RANK[row["status"]], row["adapter"].casefold(), row["source"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "row_count": len(rows),
            "healthy_count": sum(1 for row in rows if row["status"] == "healthy"),
            "warning_count": sum(1 for row in rows if row["status"] == "warning"),
            "critical_count": sum(1 for row in rows if row["status"] == "critical"),
            "warning_success_rate": warning,
            "critical_success_rate": critical,
        },
        "rows": rows,
    }


def _rollup_status(success_rate: float, warning: float, critical: float) -> str:
    if success_rate < critical:
        return "critical"
    if success_rate < warning:
        return "warning"
    return "healthy"


def _status(raw: dict[str, Any]) -> str:
    return _text(raw.get("status") or raw.get("result") or raw.get("state") or raw.get("outcome")).lower().replace("_", " ")


def _ratio(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
