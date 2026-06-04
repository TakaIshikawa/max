"""Publisher webhook failure taxonomy export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.publisher_webhook_failure_taxonomy_report.v1"
KIND = "max.publisher_webhook_failure_taxonomy_report"
DEFAULT_GENERATED_AT = "2026-06-05T00:00:00+00:00"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def generate_publisher_webhook_failure_taxonomy_report(records: Iterable[dict[str, Any]], *, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"retryable": 0, "terminal": 0, "latest": ""})
    for item in records:
        destination = _text(item.get("destination") or item.get("destination_id") or item.get("url")) or "unknown"
        reason = _text(item.get("reason") or item.get("failure_reason") or item.get("code") or item.get("status_code")).casefold() or "unknown"
        retryable = bool(item.get("retryable"))
        groups[(destination, reason)]["retryable" if retryable else "terminal"] += 1
        groups[(destination, reason)]["latest"] = max(groups[(destination, reason)]["latest"], _text(item.get("failed_at") or item.get("timestamp")))
    rows = []
    for (destination, reason), values in groups.items():
        status = "critical" if values["terminal"] else "warning" if values["retryable"] else "ok"
        rows.append({"destination": destination, "failure_reason": reason, "retryable_failure_count": values["retryable"], "terminal_failure_count": values["terminal"], "failure_count": values["retryable"] + values["terminal"], "latest_failure_at": values["latest"] or None, "status": status})
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["failure_count"], row["destination"], row["failure_reason"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"failure_count": sum(row["failure_count"] for row in rows), "destination_count": len({row["destination"] for row in rows}), "retryable_failure_count": sum(row["retryable_failure_count"] for row in rows), "terminal_failure_count": sum(row["terminal_failure_count"] for row in rows)}, "rows": rows}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
