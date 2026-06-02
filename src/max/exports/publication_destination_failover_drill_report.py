"""Publication destination failover drill export report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.publication_destination_failover_drill_report.v1"
KIND = "max.publication_destination_failover_drill_report"

SEVERITY = {"failed_drill": 0, "missing_drill": 1, "stale_successful_drill": 2, "healthy": 3}


def generate_publication_destination_failover_drill_report(
    records: Iterable[dict[str, Any]],
    *,
    stale_after_days: int = 90,
) -> dict[str, Any]:
    """Summarize destination failover drill readiness from mapping-style records."""
    rows = [_row(raw, index, stale_after_days) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["severity_rank"], row["destination"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "destination_count": len(rows),
            "risky_destination_count": sum(1 for row in rows if row["reason"] != "healthy"),
            "failed_drill_count": sum(1 for row in rows if row["reason"] == "failed_drill"),
            "stale_drill_count": sum(1 for row in rows if row["reason"] == "stale_successful_drill"),
        },
        "drill_rows": rows,
    }


def _row(raw: dict[str, Any], index: int, stale_after_days: int) -> dict[str, Any]:
    destination = _text(raw.get("destination") or raw.get("destination_id") or raw.get("publisher_destination")) or f"destination-{index}"
    fallback = _text(raw.get("fallback_destination") or raw.get("fallback") or raw.get("secondary_destination")) or None
    outcome = _outcome(raw.get("outcome") or raw.get("last_drill_outcome") or raw.get("status"))
    drilled_at = _dt(raw.get("last_drill_at") or raw.get("drill_at") or raw.get("tested_at"))
    days_since = None if drilled_at is None else max(0, (_now() - drilled_at).days)
    reason = _reason(outcome, days_since, stale_after_days)
    return {
        "destination": destination,
        "fallback_destination": fallback,
        "last_drill_at": drilled_at.isoformat() if drilled_at else None,
        "days_since_drill": days_since,
        "outcome": outcome,
        "reason": reason,
        "severity_rank": SEVERITY[reason],
    }


def _reason(outcome: str, days_since: int | None, stale_after_days: int) -> str:
    if days_since is None:
        return "missing_drill"
    if outcome == "failed":
        return "failed_drill"
    if outcome == "success" and days_since > max(0, int(stale_after_days)):
        return "stale_successful_drill"
    return "healthy"


def _outcome(value: Any) -> str:
    outcome = _text(value).casefold().replace("-", "_").replace(" ", "_")
    if outcome in {"failed", "failure", "error"}:
        return "failed"
    if outcome in {"success", "successful", "passed", "pass"}:
        return "success"
    if outcome in {"skipped", "pending"}:
        return outcome
    return "unknown"


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
