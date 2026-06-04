"""Source credential expiry export report."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_VERSION = "max.source_credential_expiry_report.v1"
KIND = "max.source_credential_expiry_report"


def build_source_credential_expiry_report(records: list[Mapping[str, Any]], *, generated_at: str = "2026-06-01T00:00:00+00:00", rotation_due_days: int = 14) -> dict[str, Any]:
    now = _dt(generated_at) or datetime.now(timezone.utc)
    rows = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        expires_at = _dt(record.get("expires_at"))
        days = _int(record.get("days_until_expiry")) if record.get("days_until_expiry") is not None else ((expires_at - now).days if expires_at else None)
        status = _status(days, rotation_due_days)
        source = _text(record.get("source") or record.get("adapter") or record.get("provider")) or "unknown-source"
        owner = _text(record.get("owner"))
        row = {
            "source": source,
            "adapter": _text(record.get("adapter")) or source,
            "provider": _text(record.get("provider")) or source,
            "credential_type": _text(record.get("credential_type") or record.get("type")) or "unknown-credential-type",
            "credential_id": _text(record.get("credential_id") or record.get("id")) or "unknown-credential",
            "expires_at": expires_at.isoformat() if expires_at else None,
            "days_until_expiry": days,
            "owner": owner or "unassigned",
            "rotation_status": _text(record.get("rotation_status")) or status,
            "severity": _text(record.get("severity")) or _severity(status),
            "rotation_runbook": _text(record.get("rotation_runbook")) or "document rotation runbook before rotating credential",
            "status": status,
        }
        rows.append(row)
    rows.sort(key=lambda row: (_status_rank(row["status"]), row["days_until_expiry"] if row["days_until_expiry"] is not None else 999999, row["source"].lower(), row["credential_id"].lower()))
    owner_counts = Counter(row["owner"] for row in rows)
    source_counts = Counter(row["source"] for row in rows)
    actions = [f"{row['source']} / {row['credential_id']}: {row['rotation_runbook']}" for row in rows if row["status"] in {"expired", "rotation_due"}]
    earliest = next((row["expires_at"] for row in rows if row["expires_at"]), None)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at,
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
        "owner_totals": _counter_rows(owner_counts, "owner"),
        "source_totals": _counter_rows(source_counts, "source"),
        "credential_rows": rows,
        "rotation_actions": actions,
    }


def generate_source_credential_expiry_report(records: list[Mapping[str, Any]], *, generated_at: str = "2026-06-01T00:00:00+00:00", rotation_due_days: int = 14) -> dict[str, Any]:
    return build_source_credential_expiry_report(records, generated_at=generated_at, rotation_due_days=rotation_due_days)


def render_source_credential_expiry_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_credential_expiry_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Source Credential Expiry Report", "", "## Rotation Actions", ""]
    lines.extend([f"- {action}" for action in report.get("rotation_actions") or []] or ["- No credential rotation actions are due."])
    return "\n".join(lines).rstrip() + "\n"


def _status(days: int | None, rotation_due_days: int) -> str:
    if days is None:
        return "rotation_due"
    if days < 0:
        return "expired"
    if days <= rotation_due_days:
        return "rotation_due"
    return "valid"


def _status_rank(status: str) -> int:
    return {"expired": 0, "rotation_due": 1, "valid": 2}.get(status, 3)


def _severity(status: str) -> str:
    return {"expired": "critical", "rotation_due": "warning", "valid": "info"}.get(status, "warning")


def _counter_rows(counter: Counter[str], key: str) -> list[dict[str, Any]]:
    return [{key: name, "count": count} for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0].lower()))]


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
