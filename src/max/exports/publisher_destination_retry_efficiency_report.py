"""Publisher destination retry efficiency export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.publisher_destination_retry_efficiency_report.v1"
KIND = "max.publisher_destination_retry_efficiency_report"
RISK_RANK = {"high": 0, "medium": 1, "low": 2}


def generate_publisher_destination_retry_efficiency_report(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, int]] = defaultdict(lambda: {"attempts": 0, "successes": 0, "successful_attempt_sum": 0, "exhausted": 0})
    for raw in events:
        destination = _text(raw.get("destination") or raw.get("destination_id") or raw.get("url")) or "unknown-destination"
        attempts = max(1, _int(raw.get("attempts") or raw.get("attempt_count") or raw.get("retry_count")) or 1)
        status = _text(raw.get("status") or raw.get("outcome")).lower()
        success = raw.get("success") is True or status in {"success", "succeeded", "delivered", "ok"}
        exhausted = raw.get("exhausted") is True or status in {"exhausted", "failed_exhausted", "retry_exhausted"}
        group = groups[destination]
        group["attempts"] += attempts
        if success:
            group["successes"] += 1
            group["successful_attempt_sum"] += attempts
        if exhausted:
            group["exhausted"] += 1
    rows = []
    for destination, group in groups.items():
        success_rate = _ratio(group["successes"], group["successes"] + group["exhausted"])
        avg_attempts = round(group["successful_attempt_sum"] / group["successes"], 2) if group["successes"] else 0.0
        risk = _risk(success_rate, avg_attempts, group["exhausted"])
        rows.append({"destination": destination, "retry_success_rate": success_rate, "average_attempts_before_success": avg_attempts, "exhausted_retry_count": group["exhausted"], "attempt_count": group["attempts"], "success_count": group["successes"], "efficiency_risk": risk})
    rows.sort(key=lambda row: (RISK_RANK[row["efficiency_risk"]], -row["exhausted_retry_count"], -row["average_attempts_before_success"], row["destination"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"destination_count": len(rows), "exhausted_retry_count": sum(r["exhausted_retry_count"] for r in rows), "high_risk_count": sum(1 for r in rows if r["efficiency_risk"] == "high")}, "rows": rows}


def _risk(success_rate: float, avg_attempts: float, exhausted: int) -> str:
    if exhausted == 1 and success_rate == 0.0:
        return "medium"
    if exhausted >= 2 or success_rate < 0.5 or avg_attempts >= 5:
        return "high"
    if exhausted or success_rate < 0.8 or avg_attempts >= 3:
        return "medium"
    return "low"


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
