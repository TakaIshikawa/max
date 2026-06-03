"""Spec publication rollback readiness export report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_publication_rollback_readiness_report.v1"
KIND = "max.spec_publication_rollback_readiness_report"
SEVERITY_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def generate_spec_publication_rollback_readiness_report(
    records: Iterable[dict[str, Any]],
    *,
    as_of: str | datetime | None = None,
    stale_after_days: int = 90,
) -> dict[str, Any]:
    now = _dt(as_of) or datetime.now(timezone.utc)
    rows = [_row(raw, index, now, stale_after_days) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["severity_rank"], -(row["days_since_rollback_test"] or 0), row["spec_id"].casefold(), row["destination"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "spec_count": len(rows),
            "unready_spec_count": sum(1 for row in rows if row["status"] != "healthy"),
            "missing_plan_count": sum(1 for row in rows if row["reason"] in {"missing_rollback_plan", "missing_revision"}),
            "stale_test_count": sum(1 for row in rows if row["reason"] == "stale_rollback_test"),
        },
        "spec_rows": rows,
    }


def _row(raw: dict[str, Any], index: int, now: datetime, stale_after_days: int) -> dict[str, Any]:
    plan_present = _bool(raw.get("rollback_plan_present") if "rollback_plan_present" in raw else raw.get("rollback_plan"))
    revision = _text(raw.get("last_successful_revision") or raw.get("revision"))
    tested_at = _dt(raw.get("rollback_tested_at") or raw.get("last_tested_at"))
    days_since = None if tested_at is None else max(0, (now - tested_at).days)
    status, reason = _classify(plan_present, revision, days_since, stale_after_days)
    return {
        "spec_id": _text(raw.get("spec_id") or raw.get("id")) or f"spec-{index}",
        "destination": _text(raw.get("destination") or raw.get("channel")) or "unknown",
        "rollback_plan_present": plan_present,
        "last_successful_revision": revision or None,
        "rollback_tested_at": tested_at.isoformat() if tested_at else None,
        "days_since_rollback_test": days_since,
        "status": status,
        "reason": reason,
        "severity_rank": SEVERITY_RANK[status],
    }


def _classify(plan_present: bool, revision: str, days_since: int | None, stale_after_days: int) -> tuple[str, str]:
    if not plan_present:
        return "critical", "missing_rollback_plan"
    if not revision:
        return "critical", "missing_revision"
    if days_since is None or days_since > stale_after_days:
        return "warning", "stale_rollback_test"
    return "healthy", "ready"


def _dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().casefold() in {"1", "true", "yes", "y", "present"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
