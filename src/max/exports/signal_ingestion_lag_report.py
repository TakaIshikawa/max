"""Signal ingestion lag export report."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable

SCHEMA_VERSION = "max.signal_ingestion_lag_report.v1"
KIND = "max.signal_ingestion_lag_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_signal_ingestion_lag_report(records: Iterable[dict[str, Any]], *, now: str | None = None, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    rows = [_row(item, index, now) for index, item in enumerate(records, start=1)]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["lag_hours"], row["profile"], row["source"]))
    stale = [row for row in rows if row["severity"] != "ok"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at,
        "summary": {"source_count": len(rows), "stale_source_count": len(stale), "highest_severity": min((row["severity"] for row in rows), key=lambda value: SEVERITY_RANK[value], default="ok")},
        "rows": rows,
        "stale_sources": stale,
    }


def render_signal_ingestion_lag_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_signal_ingestion_lag_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Signal Ingestion Lag Report", "", f"Stale sources: {report.get('summary', {}).get('stale_source_count', 0)}", ""]
    for row in report.get("stale_sources") or []:
        lines.append(f"- {row['profile']} / {row['source']}: {row['lag_hours']}h lag ({row['severity']})")
    return "\n".join(lines).rstrip() + "\n"


def _row(item: dict[str, Any], index: int, now: str | None) -> dict[str, Any]:
    last = _text(item.get("last_signal_at") or item.get("latest_signal_at"))
    cadence = _float(item.get("expected_cadence_hours")) or 24.0
    lag = _float(item.get("lag_hours"))
    if lag == 0.0 and now and last:
        lag = max((_parse(now) - _parse(last)).total_seconds() / 3600, 0.0)
    severity = "critical" if lag >= cadence * 3 else ("warn" if lag > cadence else "ok")
    return {"profile": _text(item.get("profile")) or "default", "source": _text(item.get("source")) or f"source-{index}", "last_signal_at": last, "expected_cadence_hours": round(cadence, 2), "lag_hours": round(lag, 2), "severity": severity}


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
