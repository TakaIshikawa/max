"""Source API deprecation export report."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

SCHEMA_VERSION = "max.source_api_deprecation_report.v1"
KIND = "max.source_api_deprecation_report"
DEFAULT_GENERATED_AT = "2026-05-27"


def build_source_api_deprecation_report(records: Iterable[Mapping[str, Any]], *, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    as_of = _date(generated_at) or _date(DEFAULT_GENERATED_AT)
    rows = [_row(record, as_of) for record in records if isinstance(record, Mapping)]
    rows.sort(key=lambda row: ({"expired": 0, "deprecated": 1, "sunset_soon": 2, "scheduled": 3, "unknown": 4, "supported": 5}[row["severity"]], row["source"], row["adapter"], row["api_version"]))
    deprecated = [row for row in rows if row["severity"] != "supported"]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"source_count": len(rows), "deprecated_count": len(deprecated), "expired_count": sum(1 for row in rows if row["severity"] == "expired"), "sunset_soon_count": sum(1 for row in rows if row["severity"] == "sunset_soon")}, "rows": rows, "deprecated_sources": deprecated}


def render_source_api_deprecation_report_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_api_deprecation_report_markdown(report: Mapping[str, Any]) -> str:
    lines = ["# Source API Deprecation Report", "", "## Deprecated Sources", ""]
    rows = report.get("deprecated_sources") if isinstance(report.get("deprecated_sources"), list) else []
    lines.extend([f"- {row['source']} {row['api_version']}: {row['severity']}" for row in rows] or ["- No deprecated API versions detected."])
    return "\n".join(lines).rstrip() + "\n"


def _row(record: Mapping[str, Any], as_of: date | None) -> dict[str, Any]:
    sunset = _date(record.get("sunset_at") or record.get("sunset_date"))
    days = (sunset - as_of).days if sunset and as_of else None
    deprecated = bool(record.get("deprecated") or record.get("is_deprecated"))
    severity = _severity(deprecated, days, sunset)
    return {"source": _bucket(record.get("source") or record.get("source_id"), "unknown_source"), "adapter": _bucket(record.get("adapter"), "unknown_adapter"), "api_version": _text(record.get("api_version") or record.get("version")) or "unknown", "deprecated": deprecated, "sunset_at": sunset.isoformat() if sunset else None, "days_until_sunset": days, "severity": severity}


def _severity(deprecated: bool, days: int | None, sunset: date | None) -> str:
    if days is not None and days < 0:
        return "expired"
    if deprecated and sunset is None:
        return "deprecated"
    if days is not None and days <= 30:
        return "sunset_soon"
    if deprecated or sunset is not None:
        return "scheduled"
    return "supported"


def _date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
