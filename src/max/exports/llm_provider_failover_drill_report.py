"""LLM provider failover drill export report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.llm_provider_failover_drill_report.v1"
KIND = "max.llm_provider_failover_drill_report"
SEVERITY_RANK = {"failed_drill": 0, "missing_drill": 1, "stale_successful_drill": 2, "slow_failover": 3, "healthy": 4}


def generate_llm_provider_failover_drill_report(
    records: Iterable[dict[str, Any]],
    *,
    as_of: str | datetime | None = None,
    stale_after_days: int = 90,
    slow_latency_ms: int = 5000,
) -> dict[str, Any]:
    now = _dt(as_of) or datetime.now(timezone.utc)
    rows = [_row(raw, index, now, stale_after_days, slow_latency_ms) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["severity_rank"], row["provider"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "provider_count": len(rows),
            "risky_provider_count": sum(1 for row in rows if row["reason"] != "healthy"),
            "failed_drill_count": sum(1 for row in rows if row["reason"] == "failed_drill"),
            "stale_drill_count": sum(1 for row in rows if row["reason"] == "stale_successful_drill"),
        },
        "provider_rows": rows,
    }


def _row(raw: dict[str, Any], index: int, now: datetime, stale_after_days: int, slow_latency_ms: int) -> dict[str, Any]:
    drilled_at = _dt(raw.get("last_drill_at") or raw.get("drill_at") or raw.get("tested_at"))
    days_since = None if drilled_at is None else max(0, (now - drilled_at).days)
    outcome = _outcome(raw.get("outcome") or raw.get("last_drill_outcome") or raw.get("status"))
    latency = _int(raw.get("latency_ms") or raw.get("failover_latency_ms"))
    reason = _reason(outcome, days_since, latency, stale_after_days, slow_latency_ms)
    return {
        "provider": _text(raw.get("provider") or raw.get("primary_provider")) or f"provider-{index}",
        "fallback_provider": _text(raw.get("fallback_provider") or raw.get("fallback")) or None,
        "last_drill_at": drilled_at.isoformat() if drilled_at else None,
        "days_since_drill": days_since,
        "outcome": outcome,
        "latency_ms": latency,
        "error": _text(raw.get("error")) or None,
        "reason": reason,
        "severity_rank": SEVERITY_RANK[reason],
    }


def _reason(outcome: str, days_since: int | None, latency_ms: int, stale_after_days: int, slow_latency_ms: int) -> str:
    if days_since is None:
        return "missing_drill"
    if outcome == "failed":
        return "failed_drill"
    if outcome == "success" and days_since > stale_after_days:
        return "stale_successful_drill"
    if outcome == "success" and latency_ms > slow_latency_ms:
        return "slow_failover"
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


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
