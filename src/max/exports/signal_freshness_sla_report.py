"""Signal freshness SLA export report."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.signal_freshness_sla_report.v1"
KIND = "max.signal_freshness_sla_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


class SignalFreshnessInput(TypedDict, total=False):
    source: str
    latest_signal_at: str
    fetched_at: str
    age_hours: int | float | str
    max_age_hours: int | float | str
    signal_count: int | float | str
    severity: str


def build_signal_freshness_sla_report(
    records: Iterable[SignalFreshnessInput | dict[str, Any]],
    *,
    title: str = "Signal Freshness SLA Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = _normalize_records(records)
    stale = [row for row in rows if row["stale"]]
    remediation = sorted(stale, key=lambda row: (_SEVERITY_ORDER[row["severity"]], -row["age_hours"], row["source"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Signal Freshness SLA Report",
        "summary": {
            "source_count": len(rows),
            "stale_source_count": len(stale),
            "sla_breach_count": len(stale),
            "total_signal_count": sum(row["signal_count"] for row in rows),
            "fresh_source_count": len(rows) - len(stale),
        },
        "source_freshness": rows,
        "stale_sources": remediation,
        "remediation_actions": [
            {
                "source": row["source"],
                "severity": row["severity"],
                "age_hours": row["age_hours"],
                "action": f"Refresh {row['source']} signals and verify adapter schedule.",
            }
            for row in remediation
        ],
    }


def render_signal_freshness_sla_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Signal Freshness SLA Report'}",
        "",
        "## Summary",
        "",
        f"- Sources: {summary.get('source_count', 0)}",
        f"- Stale sources: {summary.get('stale_source_count', 0)}",
        f"- SLA breaches: {summary.get('sla_breach_count', 0)}",
        "",
        "## Remediation",
        "",
    ]
    actions = report.get("remediation_actions") or []
    if actions:
        for row in actions:
            lines.append(f"- {row['source']}: {row['action']}")
    else:
        lines.append("- No stale sources detected.")
    return "\n".join(lines).rstrip() + "\n"


def render_signal_freshness_sla_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[SignalFreshnessInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, raw in enumerate(records):
        age = _float(raw.get("age_hours"))
        if age == 0.0 and not _has_value(raw.get("age_hours")):
            age = _age_hours(raw.get("latest_signal_at"), raw.get("fetched_at"))
        max_age = _float(raw.get("max_age_hours")) or 24.0
        rows.append(
            {
                "source": _text(raw.get("source")) or "Unknown source",
                "latest_signal_at": _text(raw.get("latest_signal_at")),
                "fetched_at": _text(raw.get("fetched_at")),
                "age_hours": round(age, 2),
                "max_age_hours": round(max_age, 2),
                "signal_count": _int(raw.get("signal_count")),
                "severity": _severity(raw.get("severity")),
                "stale": age > max_age,
                "_input_order": index,
            }
        )
    rows.sort(key=lambda row: (row["source"].lower(), row["_input_order"]))
    for row in rows:
        row.pop("_input_order", None)
    return rows


def _age_hours(start: Any, end: Any) -> float:
    started = _parse_time(start)
    ended = _parse_time(end)
    if not started or not ended:
        return 0.0
    return max(0.0, (ended - started).total_seconds() / 3600)


def _parse_time(value: Any) -> datetime | None:
    text = _text(value).replace("Z", "+00:00")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _severity(value: Any) -> str:
    text = _text(value).lower()
    return text if text in _SEVERITY_ORDER else "unknown"


def _has_value(value: Any) -> bool:
    return _text(value) != ""


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
