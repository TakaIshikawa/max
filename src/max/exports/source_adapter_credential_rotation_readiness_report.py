"""Source adapter credential rotation readiness export report."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_credential_rotation_readiness_report.v1"
KIND = "max.source_adapter_credential_rotation_readiness_report"
DEFAULT_AS_OF = "2026-06-07"


def generate_source_adapter_credential_rotation_readiness_report(records: Iterable[dict[str, Any]], *, as_of: str = DEFAULT_AS_OF, due_soon_days: int = 14) -> dict[str, Any]:
    today = _date(as_of) or date(2026, 6, 7)
    rows = []
    for index, raw in enumerate(records):
        interval = _int(raw.get("rotation_interval_days"))
        rotated_at = _date(raw.get("rotated_at") or raw.get("last_rotated_at"))
        due_at = _date(raw.get("next_rotation_due_at")) or (rotated_at + timedelta(days=interval) if rotated_at and interval else None)
        missing_owner = not _text(raw.get("owner"))
        missing_policy = _bool(raw.get("missing_policy")) or interval <= 0
        status = _status(due_at=due_at, today=today, due_soon_days=due_soon_days, missing_owner=missing_owner, missing_policy=missing_policy)
        rows.append({"adapter": _text(raw.get("adapter") or raw.get("source")) or f"adapter-{index + 1}", "credential_type": _text(raw.get("credential_type")) or "unknown-credential", "owner": _text(raw.get("owner")) or "Unassigned", "rotated_at": _text(raw.get("rotated_at") or raw.get("last_rotated_at")), "next_rotation_due_at": due_at.isoformat() if due_at else "", "days_until_due": (due_at - today).days if due_at else None, "status": status})
    rows.sort(key=lambda row: ({"blocked": 0, "due_soon": 1, "ready": 2}[row["status"]], row["adapter"].lower(), row["credential_type"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"credential_count": len(rows), "ready_count": sum(1 for row in rows if row["status"] == "ready"), "due_soon_count": sum(1 for row in rows if row["status"] == "due_soon"), "blocked_count": sum(1 for row in rows if row["status"] == "blocked"), "due_soon_days": due_soon_days}, "rows": rows}


def _status(*, due_at: date | None, today: date, due_soon_days: int, missing_owner: bool, missing_policy: bool) -> str:
    if missing_owner or missing_policy or due_at is None or due_at < today:
        return "blocked"
    if due_at <= today + timedelta(days=max(0, due_soon_days)):
        return "due_soon"
    return "ready"


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "y"}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
