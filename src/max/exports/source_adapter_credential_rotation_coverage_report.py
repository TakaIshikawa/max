"""Source adapter credential rotation coverage export report."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_credential_rotation_coverage_report.v1"
KIND = "max.source_adapter_credential_rotation_coverage_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"
DEFAULT_DUE_SOON_DAYS = 14

_SEVERITY_ORDER = {"overdue": 0, "due_soon": 1, "missing_policy": 2, "unknown": 3, "covered": 4}


def build_source_adapter_credential_rotation_coverage_report(
    records: Iterable[dict[str, Any]],
    *,
    title: str = "Source Adapter Credential Rotation Coverage Report",
    generated_at: str = DEFAULT_GENERATED_AT,
    due_soon_days: int = DEFAULT_DUE_SOON_DAYS,
) -> dict[str, Any]:
    generated_on = _date(generated_at) or _date(DEFAULT_GENERATED_AT) or date(2026, 5, 27)
    rows = []
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            continue
        row = _row(raw, index=index, generated_on=generated_on, due_soon_days=max(0, due_soon_days))
        rows.append(row)
    rows.sort(key=lambda row: (_SEVERITY_ORDER[row["rotation_status"]], row["source"].lower(), row["adapter"].lower(), row["credential_type"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Source Adapter Credential Rotation Coverage Report",
        "summary": {
            "adapter_credential_count": len(rows),
            "covered_count": sum(1 for row in rows if row["rotation_status"] == "covered"),
            "overdue_count": sum(1 for row in rows if row["rotation_status"] == "overdue"),
            "due_soon_count": sum(1 for row in rows if row["rotation_status"] == "due_soon"),
            "missing_policy_count": sum(1 for row in rows if row["rotation_status"] == "missing_policy"),
            "unknown_count": sum(1 for row in rows if row["rotation_status"] == "unknown"),
        },
        "coverage_rows": rows,
    }


def render_source_adapter_credential_rotation_coverage_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_adapter_credential_rotation_coverage_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Source Adapter Credential Rotation Coverage Report'}",
        "",
        "## Summary",
        "",
        f"- Covered: {summary.get('covered_count', 0)}",
        f"- Overdue: {summary.get('overdue_count', 0)}",
        f"- Due soon: {summary.get('due_soon_count', 0)}",
        f"- Missing policy: {summary.get('missing_policy_count', 0)}",
        f"- Unknown: {summary.get('unknown_count', 0)}",
        "",
        "## Coverage",
        "",
    ]
    rows = report.get("coverage_rows") or []
    lines.extend([f"- {row['source']} / {row['adapter']} / {row['credential_type']}: {row['rotation_status']} (owner: {row['owner']})" for row in rows] or ["- No source adapter credentials reported."])
    return "\n".join(lines).rstrip() + "\n"


def _row(raw: dict[str, Any], *, index: int, generated_on: date, due_soon_days: int) -> dict[str, Any]:
    interval = _int(raw.get("rotation_interval_days"))
    rotated_at = _date(raw.get("rotated_at"))
    explicit_due = _date(raw.get("next_rotation_due_at"))
    due_at = explicit_due or (rotated_at + timedelta(days=interval) if rotated_at and interval > 0 else None)
    missing_policy = _bool(raw.get("missing_policy")) or interval <= 0
    status = _status(due_at=due_at, missing_policy=missing_policy, generated_on=generated_on, due_soon_days=due_soon_days)
    days_until_due = (due_at - generated_on).days if due_at else None
    return {
        "row_id": _text(raw.get("row_id") or raw.get("id")) or f"credential-{index + 1}",
        "source": _text(raw.get("source")) or "unknown-source",
        "adapter": _text(raw.get("adapter")) or "unknown-adapter",
        "credential_type": _text(raw.get("credential_type")) or "unknown-credential",
        "rotated_at": _text(raw.get("rotated_at")),
        "rotation_interval_days": interval,
        "next_rotation_due_at": _text(raw.get("next_rotation_due_at")) or (due_at.isoformat() if due_at else ""),
        "days_until_due": days_until_due,
        "owner": _text(raw.get("owner")) or "Unassigned",
        "missing_policy": missing_policy,
        "rotation_status": status,
    }


def _status(*, due_at: date | None, missing_policy: bool, generated_on: date, due_soon_days: int) -> str:
    if missing_policy:
        return "missing_policy"
    if due_at is None:
        return "unknown"
    if due_at < generated_on:
        return "overdue"
    if due_at <= generated_on + timedelta(days=due_soon_days):
        return "due_soon"
    return "covered"


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


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
