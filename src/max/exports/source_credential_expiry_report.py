"""Source credential expiry export report."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_VERSION = "max.source_credential_expiry_report.v1"
KIND = "max.source_credential_expiry_report"


def build_source_credential_expiry_report(
    records: list[Mapping[str, Any]],
    *,
    rotation_due_days: int = 14,
    generated_at: str = "2026-06-01T00:00:00+00:00",
    source: str = "source_credentials",
) -> dict[str, Any]:
    now = _dt(generated_at) or datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = [_row(record, index, now, rotation_due_days) for index, record in enumerate(records, start=1) if isinstance(record, Mapping)]
    rows.sort(
        key=lambda row: (
            _status_rank(row["status"]),
            row["days_until_expiry"] if row["days_until_expiry"] is not None else 999999,
            row["source"].lower(),
            row["credential_id"].lower(),
        )
    )
    owner_counts = Counter(row["owner"] for row in rows)
    source_counts = Counter(row["source"] for row in rows)
    action_rows = [
        {
            "source": row["source"],
            "credential_id": row["credential_id"],
            "owner": row["owner"],
            "action": "rotate expired credential" if row["status"] == "expired" else "schedule credential rotation",
            "rotation_runbook": row["rotation_runbook"],
        }
        for row in rows
        if row["status"] in {"expired", "rotation_due"}
    ]
    actions = [_action_text(row) for row in action_rows]
    earliest = min((row["expires_at"] for row in rows if row["expires_at"]), default=None)
    owner_summary = _counter_rows(owner_counts, "owner", sort_by_count=False)
    source_summary = _counter_rows(source_counts, "source", sort_by_count=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at,
        "source": source,
        "summary": {
            "credential_count": len(rows),
            "total_source_count": len({row["source"] for row in rows}),
            "expired_count": sum(1 for row in rows if row["status"] == "expired"),
            "rotation_due_count": sum(1 for row in rows if row["status"] == "rotation_due"),
            "expiring_count": sum(1 for row in rows if row["status"] == "rotation_due"),
            "valid_count": sum(1 for row in rows if row["status"] == "valid"),
            "healthy_count": sum(1 for row in rows if row["status"] == "valid"),
            "missing_owner_count": sum(1 for row in rows if row["owner"] == "unassigned"),
            "earliest_expiry_at": earliest,
        },
        "credential_rows": rows,
        "owner_summary": owner_summary,
        "source_summary": source_summary,
        "owner_totals": _counter_rows(owner_counts, "owner", sort_by_count=True),
        "source_totals": _counter_rows(source_counts, "source", sort_by_count=True),
        "rotation_actions": actions,
        "rotation_action_rows": action_rows,
    }


def generate_source_credential_expiry_report(
    records: list[Mapping[str, Any]],
    *,
    generated_at: str = "2026-06-01T00:00:00+00:00",
    rotation_due_days: int = 14,
    source: str = "source_credentials",
) -> dict[str, Any]:
    return build_source_credential_expiry_report(records, generated_at=generated_at, rotation_due_days=rotation_due_days, source=source)


def render_source_credential_expiry_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_credential_expiry_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Source Credential Expiry Report", "", "## Rotation Actions", ""]
    actions = report.get("rotation_actions") or []
    lines.extend([f"- {action}" for action in actions] or ["- No credential rotation actions required. No credential rotation actions are due."])
    lines.extend(["", "## Credentials", ""])
    lines.extend(
        [f"- {row['source']} / {row['credential_id']}: {row['status']} ({row['days_until_expiry']} days)" for row in report.get("credential_rows") or []]
        or ["- No credential records supplied."]
    )
    return "\n".join(lines).rstrip() + "\n"


def _row(record: Mapping[str, Any], index: int, now: datetime, rotation_due_days: int) -> dict[str, Any]:
    expires_at_dt = _dt(record.get("expires_at"))
    days = _days(record.get("days_until_expiry"), expires_at_dt, now)
    hint = _text(record.get("rotation_status") or record.get("severity")).lower()
    status = _status(days, rotation_due_days, hint)
    source = _text(record.get("source") or record.get("adapter") or record.get("provider")) or f"source-{index}"
    rotation_runbook = _text(record.get("rotation_runbook") or record.get("runbook")) or "document rotation runbook"
    return {
        "source": source,
        "adapter": _text(record.get("adapter")) or source,
        "provider": _text(record.get("provider")) or source,
        "credential_type": _text(record.get("credential_type") or record.get("type")) or "unknown-credential-type",
        "credential_id": _text(record.get("credential_id") or record.get("id")) or f"credential-{index}",
        "expires_at": expires_at_dt.isoformat() if expires_at_dt else None,
        "days_until_expiry": days,
        "owner": _text(record.get("owner")) or "unassigned",
        "rotation_status": _text(record.get("rotation_status")) or status,
        "severity": _text(record.get("severity")) or _severity(status),
        "rotation_runbook": rotation_runbook,
        "status": status,
    }


def _action_text(action: Mapping[str, Any]) -> str:
    runbook = _text(action.get("rotation_runbook"))
    default_runbook = runbook == "document rotation runbook"
    detail = _text(action.get("action")) if default_runbook else runbook
    suffix = f" ({action['owner']})" if default_runbook else ""
    return f"{action['source']} / {action['credential_id']}: {detail}{suffix}"


def _status(days: int | None, rotation_due_days: int, hint: str = "") -> str:
    if hint in {"expired"}:
        return "expired"
    if hint in {"rotation_due", "expiring"}:
        return "rotation_due"
    if days is None:
        return "rotation_due"
    if days < 0:
        return "expired"
    if days <= rotation_due_days:
        return "rotation_due"
    return "valid"


def _days(value: Any, expires_at: datetime | None, now: datetime) -> int | None:
    if value is not None:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            pass
    return (expires_at - now).days if expires_at else None


def _dt(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _status_rank(status: str) -> int:
    return {"expired": 0, "rotation_due": 1, "valid": 2}.get(status, 3)


def _severity(status: str) -> str:
    return {"expired": "critical", "rotation_due": "warning", "valid": "info"}.get(status, "warning")


def _counter_rows(counter: Counter[str], key: str, *, sort_by_count: bool) -> list[dict[str, Any]]:
    if sort_by_count:
        items = sorted(counter.items(), key=lambda item: (-item[1], item[0].lower()))
    else:
        items = sorted(counter.items(), key=lambda item: item[0].lower())
    return [{key: name, "count": count} for name, count in items]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
