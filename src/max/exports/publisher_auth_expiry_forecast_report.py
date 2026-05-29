"""Publisher auth expiry forecast export report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.publisher_auth_expiry_forecast_report.v1"
KIND = "max.publisher_auth_expiry_forecast_report"


def generate_publisher_auth_expiry_forecast_report(records: Iterable[dict[str, Any]], *, now: str = "2026-05-29T00:00:00+00:00", warning_days: int = 30, title: str = "Publisher Auth Expiry Forecast Report") -> dict[str, Any]:
    now_dt = _dt(now)
    rows = []
    for raw in records:
        if not isinstance(raw, dict):
            continue
        expires_at = _text(raw.get("expires_at") or raw.get("expiration") or raw.get("expiry"))
        days = (_dt(expires_at) - now_dt).days if expires_at else 999999
        if days > warning_days:
            continue
        severity = "critical" if days < 0 else "high" if days <= 7 else "medium"
        rows.append({"publisher": _text(raw.get("publisher")) or "unknown-publisher", "destination": _text(raw.get("destination")) or "unknown-destination", "profile": _text(raw.get("profile")) or "unknown-profile", "expires_at": expires_at or "unknown", "days_until_expiry": days, "last_success_at": _text(raw.get("last_success_at")) or "unknown", "severity": severity, "recommended_action": "Rotate expired credential before next publication." if days < 0 else "Schedule credential rotation inside warning window."})
    rows.sort(key=lambda r: (r["days_until_expiry"], _severity_rank(r["severity"]), r["publisher"].lower(), r["destination"].lower(), r["profile"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "title": title, "summary": {"row_count": len(rows), "expired_count": sum(1 for r in rows if r["days_until_expiry"] < 0), "warning_days": warning_days}, "rows": rows}


def render_publisher_auth_expiry_forecast_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_publisher_auth_expiry_forecast_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Publisher Auth Expiry Forecast Report'}", "", "## Summary", "", f"- Credentials: {report.get('summary', {}).get('row_count', 0)}", "", "## Expiry Rows", ""]
    rows = report.get("rows") or []
    lines.extend([f"- {r['publisher']} / {r['destination']} / {r['profile']}: {r['expires_at']} ({r['severity']})" for r in rows] or ["- No credentials inside the warning window."])
    return "\n".join(lines).rstrip() + "\n"


def _dt(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime(9999, 1, 1, tzinfo=timezone.utc)


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
