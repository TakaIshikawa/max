"""Publisher retry backlog export report."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.publisher_retry_backlog_report.v1"
KIND = "max.publisher_retry_backlog_report"
DEFAULT_AS_OF = "2026-05-20"


class PublisherRetryFailureInput(TypedDict, total=False):
    destination: str
    target: str
    error_class: str
    error: str
    failed_at: str
    next_retry_at: str
    retry_count: int | float | str
    owner: str


def build_publisher_retry_backlog_report(records: Iterable[PublisherRetryFailureInput | dict[str, Any]], *, title: str = "Publisher Retry Backlog Report", as_of: str = DEFAULT_AS_OF) -> dict[str, Any]:
    rows = _normalize_records(records, as_of=as_of)
    overdue = [row for row in rows if row["retry_status"] == "overdue"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Publisher Retry Backlog Report",
        "as_of": _text(as_of) or DEFAULT_AS_OF,
        "summary": {"failure_count": len(rows), "destination_count": len({row["destination"] for row in rows}), "overdue_retry_count": len(overdue)},
        "destination_totals": _destination_totals(rows),
        "error_class_totals": [{"error_class": name, "count": count} for name, count in sorted(Counter(row["error_class"] for row in rows).items())],
        "overdue_retries": sorted(overdue, key=lambda row: (-row["retry_age_days"], row["destination"].lower(), row["failure_id"])),
        "next_actions": [{"destination": row["destination"], "failure_id": row["failure_id"], "action": _action(row)} for row in rows if row["retry_status"] in {"overdue", "unscheduled"}],
        "failures": rows,
    }


def render_publisher_retry_backlog_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Publisher Retry Backlog Report'}",
        "",
        "## Summary",
        "",
        f"- Failed attempts: {summary.get('failure_count', 0)}",
        f"- Overdue retries: {summary.get('overdue_retry_count', 0)}",
        "",
        "## Overdue Retries",
        "",
    ]
    overdue = report.get("overdue_retries") or []
    if not overdue:
        lines.append("- No overdue publisher retries.")
    else:
        for row in overdue:
            lines.append(f"- {row['destination']} {row['failure_id']}: {row['error_class']} ({row['retry_age_days']} days)")
    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions") or []
    lines.extend([f"- {row['destination']}: {row['action']}" for row in actions] or ["- No retry actions required."])
    return "\n".join(lines).rstrip() + "\n"


def render_publisher_retry_backlog_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[PublisherRetryFailureInput | dict[str, Any]], *, as_of: str) -> list[dict[str, Any]]:
    as_of_date = _date(as_of) or date(2026, 5, 20)
    rows = []
    for index, raw in enumerate(records):
        next_retry = _date(raw.get("next_retry_at"))
        failed = _date(raw.get("failed_at"))
        retry_age = (as_of_date - (next_retry or failed or as_of_date)).days
        rows.append({"failure_id": _text(raw.get("failure_id")) or f"failure-{index + 1}", "destination": _text(raw.get("destination") or raw.get("target")) or "Unspecified destination", "error_class": _text(raw.get("error_class") or raw.get("error")) or "unknown_error", "failed_at": _text(raw.get("failed_at")), "next_retry_at": _text(raw.get("next_retry_at")), "retry_count": _int(raw.get("retry_count")), "owner": _text(raw.get("owner")) or "Unassigned", "retry_age_days": max(retry_age, 0), "retry_status": "unscheduled" if not next_retry else ("overdue" if next_retry < as_of_date else "scheduled")})
    rows.sort(key=lambda row: (row["destination"].lower(), row["error_class"].lower(), row["failure_id"]))
    return rows


def _destination_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    destinations = sorted({row["destination"] for row in rows}, key=str.lower)
    return [{"destination": destination, "failure_count": sum(1 for row in rows if row["destination"] == destination), "overdue_retry_count": sum(1 for row in rows if row["destination"] == destination and row["retry_status"] == "overdue")} for destination in destinations]


def _action(row: dict[str, Any]) -> str:
    return "Schedule retry window and owner." if row["retry_status"] == "unscheduled" else f"Retry now or reclassify {row['error_class']} failure."


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
