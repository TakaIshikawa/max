"""Profile source reliability export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.profile_source_reliability_report.v1"
KIND = "max.profile_source_reliability_report"
RISK_RANK = {"high": 0, "medium": 1, "low": 2}


def generate_profile_source_reliability_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"attempts": 0, "successes": 0, "timeouts": 0, "circuit_open": 0})
    for raw in records:
        profile = _text(raw.get("profile_id") or raw.get("profile")) or "unknown-profile"
        source = _text(raw.get("source") or raw.get("source_id") or raw.get("adapter")) or "unknown-source"
        group = groups[(profile, source)]
        attempts = _int(raw.get("attempts") or raw.get("attempt_count"))
        successes = _int(raw.get("successes") or raw.get("success_count"))
        if attempts == 0:
            attempts = 1
            status = _text(raw.get("status") or raw.get("outcome")).lower()
            successes = 1 if status in {"success", "succeeded", "ok"} or raw.get("success") is True else successes
        group["attempts"] += attempts
        group["successes"] += min(successes, attempts)
        status_text = _text(raw.get("status") or raw.get("error") or raw.get("failure_reason")).lower()
        group["timeouts"] += _int(raw.get("timeout_count")) + (1 if "timeout" in status_text else 0)
        group["circuit_open"] += _int(raw.get("circuit_open_count")) + (1 if _bool(raw.get("circuit_open")) or "circuit" in status_text else 0)
    rows = []
    for (profile, source), group in groups.items():
        success_rate = _ratio(group["successes"], group["attempts"])
        risk = _risk(success_rate, group["timeouts"], group["circuit_open"])
        rows.append({"profile_id": profile, "source": source, "attempt_count": group["attempts"], "success_count": group["successes"], "success_rate": success_rate, "timeout_count": group["timeouts"], "circuit_open_count": group["circuit_open"], "reliability_risk": risk})
    rows.sort(key=lambda row: (RISK_RANK[row["reliability_risk"]], row["success_rate"], row["profile_id"].lower(), row["source"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "attempt_count": sum(r["attempt_count"] for r in rows), "high_risk_count": sum(1 for r in rows if r["reliability_risk"] == "high")}, "rows": rows}


def _risk(success_rate: float, timeouts: int, circuit_open: int) -> str:
    if 0 < timeouts < 3 and success_rate == 0.0:
        return "medium"
    if circuit_open > 0 or timeouts >= 3 or success_rate < 0.5:
        return "high"
    if timeouts > 0 or success_rate < 0.8:
        return "medium"
    return "low"


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "y"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
