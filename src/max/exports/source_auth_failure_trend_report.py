"""Source authentication failure trend export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.source_auth_failure_trend_report.v1"
KIND = "max.source_auth_failure_trend_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


class SourceAuthFailureTrendInput(TypedDict, total=False):
    source: str
    adapter: str
    credential_scope: str
    timestamp: str
    day: str
    error_code: str
    failure_count: int | float | str
    recovered: bool
    recovery_status: str


def build_source_auth_failure_trend_report(
    records: Iterable[SourceAuthFailureTrendInput | dict[str, Any]] | dict[str, Any],
    *,
    title: str = "Source Auth Failure Trend Report",
    generated_at: str = DEFAULT_GENERATED_AT,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = _rows(records)
    unresolved = [row for row in rows if row["recovery_status"] == "unresolved"]
    recovered = [row for row in rows if row["recovery_status"] == "recovered"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Source Auth Failure Trend Report",
        "metadata": dict(metadata or {}),
        "summary": {
            "failure_count": sum(row["failure_count"] for row in rows),
            "affected_source_count": len({row["source"] for row in rows}),
            "unresolved_count": sum(row["failure_count"] for row in unresolved),
            "recovered_count": sum(row["failure_count"] for row in recovered),
            "row_count": len(rows),
        },
        "failure_rows": rows,
        "unresolved_failures": unresolved,
        "recovered_failures": recovered,
        "top_affected_sources": _source_totals(rows),
    }


def render_source_auth_failure_trend_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_auth_failure_trend_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Source Auth Failure Trend Report'}",
        "",
        "## Summary",
        "",
        f"- Failures: {summary.get('failure_count', 0)}",
        f"- Affected sources: {summary.get('affected_source_count', 0)}",
        f"- Unresolved failures: {summary.get('unresolved_count', 0)}",
        f"- Recovered failures: {summary.get('recovered_count', 0)}",
        "",
        "## Top Affected Sources",
        "",
    ]
    totals = report.get("top_affected_sources") or []
    lines.extend(
        [
            f"- {row['source']}: {row['failure_count']} failures, {row['unresolved_count']} unresolved"
            for row in totals[:10]
        ]
        or ["- No authentication failures detected."]
    )
    return "\n".join(lines).rstrip() + "\n"


def _rows(records: Iterable[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    source = records.get("failures") if isinstance(records, dict) else records
    grouped: dict[tuple[str, str, str, str, str, str], int] = defaultdict(int)
    for raw in source or []:
        if not isinstance(raw, dict):
            continue
        key = (
            _text(raw.get("source") or raw.get("source_name")) or "unknown-source",
            _text(raw.get("adapter") or raw.get("adapter_name")) or "unknown-adapter",
            _text(raw.get("credential_scope") or raw.get("scope")) or "default",
            _day(raw.get("day") or raw.get("timestamp") or raw.get("occurred_at")),
            _text(raw.get("error_code") or raw.get("code")) or "auth_failure",
            _status(raw),
        )
        grouped[key] += _int(raw.get("failure_count", raw.get("count", 1)))
    rows = [
        {
            "source": source,
            "adapter": adapter,
            "credential_scope": scope,
            "day": day,
            "error_code": code,
            "recovery_status": status,
            "failure_count": count,
        }
        for (source, adapter, scope, day, code, status), count in grouped.items()
    ]
    rows.sort(key=lambda row: (row["source"].lower(), row["day"], row["adapter"].lower(), row["credential_scope"].lower(), row["error_code"].lower(), row["recovery_status"]))
    return rows


def _source_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        total = totals.setdefault(row["source"], {"source": row["source"], "failure_count": 0, "unresolved_count": 0, "recovered_count": 0})
        total["failure_count"] += row["failure_count"]
        if row["recovery_status"] == "unresolved":
            total["unresolved_count"] += row["failure_count"]
        else:
            total["recovered_count"] += row["failure_count"]
    result = list(totals.values())
    result.sort(key=lambda row: (-row["failure_count"], -row["unresolved_count"], row["source"].lower()))
    return result


def _status(raw: dict[str, Any]) -> str:
    status = _text(raw.get("recovery_status") or raw.get("status")).lower().replace(" ", "_")
    if status in {"recovered", "resolved", "fixed"}:
        return "recovered"
    if raw.get("recovered") is True or raw.get("resolved") is True:
        return "recovered"
    return "unresolved"


def _day(value: Any) -> str:
    text = _text(value)
    return text[:10] if text else "unknown-day"


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
