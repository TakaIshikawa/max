"""Prompt injection attempt trend export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.prompt_injection_attempt_trend_report.v1"
KIND = "max.prompt_injection_attempt_trend_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


def build_prompt_injection_attempt_trend_report(
    records: Iterable[dict[str, Any]],
    *,
    title: str = "Prompt Injection Attempt Trend Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, bool, str], int] = defaultdict(int)
    for raw in records:
        key = (
            _date(raw.get("occurred_at") or raw.get("timestamp") or raw.get("date")),
            _text(raw.get("source")) or "unknown-source",
            _text(raw.get("profile")) or "unknown-profile",
            _severity(raw.get("severity")),
            _bool(raw.get("blocked")),
        )
        grouped[key] += _int(raw.get("attempt_count")) or 1

    rows = [
        {
            "date": date,
            "source": source,
            "profile": profile,
            "severity": severity,
            "blocked": blocked,
            "attempt_count": count,
        }
        for (date, source, profile, severity, blocked), count in grouped.items()
    ]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["date"], row["source"].lower(), row["profile"].lower(), not row["blocked"]))
    total = sum(row["attempt_count"] for row in rows)
    blocked = sum(row["attempt_count"] for row in rows if row["blocked"])
    critical = sum(row["attempt_count"] for row in rows if row["severity"] == "critical")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Prompt Injection Attempt Trend Report",
        "summary": {
            "total_attempt_count": total,
            "blocked_count": blocked,
            "critical_attempt_count": critical,
            "source_count": len({row["source"] for row in rows}),
            "profile_count": len({row["profile"] for row in rows}),
            "day_count": len({row["date"] for row in rows}),
        },
        "attempt_trends": rows,
    }


def render_prompt_injection_attempt_trend_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_prompt_injection_attempt_trend_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Prompt Injection Attempt Trend Report'}",
        "",
        "## Summary",
        "",
        f"- Total attempts: {summary.get('total_attempt_count', 0)}",
        f"- Blocked attempts: {summary.get('blocked_count', 0)}",
        f"- Critical attempts: {summary.get('critical_attempt_count', 0)}",
        "",
        "## Trend Rows",
        "",
    ]
    rows = report.get("attempt_trends") or []
    if not rows:
        lines.append("- No prompt injection attempts were found.")
    for row in rows:
        lines.append(f"- {row['date']} {row['severity']} {row['source']} ({row['profile']}): {row['attempt_count']} attempts, blocked={row['blocked']}")
    return "\n".join(lines).rstrip() + "\n"


def _severity(value: Any) -> str:
    severity = (_text(value) or "unknown").lower()
    return severity if severity in SEVERITY_RANK else "unknown"


def _date(value: Any) -> str:
    text = _text(value)
    return text[:10] if text else "unknown-date"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "blocked"}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
