"""Publication approval queue aging export report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.publication_approval_queue_aging_report.v1"
KIND = "max.publication_approval_queue_aging_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"
DEFAULT_AGING_HOURS = 24
DEFAULT_STALE_HOURS = 72

_STATUS_ORDER = {"stale": 0, "aging": 1, "fresh": 2, "approved": 3, "rejected": 4}


def build_publication_approval_queue_aging_report(
    records: Iterable[dict[str, Any]],
    *,
    title: str = "Publication Approval Queue Aging Report",
    generated_at: str = DEFAULT_GENERATED_AT,
    aging_hours: int = DEFAULT_AGING_HOURS,
    stale_hours: int = DEFAULT_STALE_HOURS,
) -> dict[str, Any]:
    generated = _datetime(generated_at) or _datetime(DEFAULT_GENERATED_AT) or datetime(2026, 5, 27, tzinfo=timezone.utc)
    rows = []
    for index, raw in enumerate(records):
        if isinstance(raw, dict):
            rows.append(_row(raw, index=index, generated=generated, aging_hours=max(0, aging_hours), stale_hours=max(0, stale_hours)))
    rows.sort(key=lambda row: (_STATUS_ORDER[row["age_bucket"]], -row["age_hours"], row["destination"].lower(), row["spec_id"].lower()))
    pending = [row for row in rows if row["status"] == "pending"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Publication Approval Queue Aging Report",
        "summary": {
            "approval_count": len(rows),
            "pending_count": len(pending),
            "stale_count": sum(1 for row in pending if row["age_bucket"] == "stale"),
            "aging_count": sum(1 for row in pending if row["age_bucket"] == "aging"),
            "approved_count": sum(1 for row in rows if row["status"] == "approved"),
            "rejected_count": sum(1 for row in rows if row["status"] == "rejected"),
        },
        "approval_rows": rows,
    }


def render_publication_approval_queue_aging_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_publication_approval_queue_aging_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Publication Approval Queue Aging Report'}",
        "",
        "## Summary",
        "",
        f"- Pending: {summary.get('pending_count', 0)}",
        f"- Stale: {summary.get('stale_count', 0)}",
        f"- Aging: {summary.get('aging_count', 0)}",
        f"- Approved: {summary.get('approved_count', 0)}",
        f"- Rejected: {summary.get('rejected_count', 0)}",
        "",
        "## Queue",
        "",
    ]
    rows = report.get("approval_rows") or []
    lines.extend([f"- {row['spec_id']} -> {row['destination']}: {row['age_bucket']} ({row['age_hours']}h, reviewer: {row['reviewer']})" for row in rows] or ["- No publication approvals reported."])
    return "\n".join(lines).rstrip() + "\n"


def _row(raw: dict[str, Any], *, index: int, generated: datetime, aging_hours: int, stale_hours: int) -> dict[str, Any]:
    status = _status(raw.get("status"))
    requested = _datetime(raw.get("requested_at"))
    age_hours = max(0, int((generated - requested).total_seconds() // 3600)) if requested else 0
    bucket = _bucket(status=status, age_hours=age_hours, requested=requested, aging_hours=aging_hours, stale_hours=stale_hours)
    return {
        "spec_id": _text(raw.get("spec_id") or raw.get("id")) or f"spec-{index + 1}",
        "destination": _text(raw.get("destination")) or "unspecified-destination",
        "requested_at": _text(raw.get("requested_at")),
        "reviewer": _text(raw.get("reviewer")) or "Unassigned",
        "priority": _text(raw.get("priority")) or "normal",
        "status": status,
        "escalation_owner": _text(raw.get("escalation_owner")) or "",
        "age_hours": age_hours,
        "age_bucket": bucket,
    }


def _bucket(*, status: str, age_hours: int, requested: datetime | None, aging_hours: int, stale_hours: int) -> str:
    if status in {"approved", "rejected"}:
        return status
    if requested is None:
        return "aging"
    if age_hours >= stale_hours:
        return "stale"
    if age_hours >= aging_hours:
        return "aging"
    return "fresh"


def _status(value: Any) -> str:
    status = _text(value).lower()
    return status if status in {"pending", "approved", "rejected"} else "pending"


def _datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
