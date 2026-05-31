"""Signal source reliability export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_signal_source_reliability_report(fetch_runs: Iterable[dict[str, Any]], *, warning_failure_rate: float = 0.1, critical_failure_rate: float = 0.25) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in fetch_runs:
        source = _text(run.get("source")) or "unknown"
        profile = _text(run.get("profile")) or "default"
        groups[(source, profile)].append(dict(run))
    rows = []
    for (source, profile), runs in groups.items():
        ordered = sorted(runs, key=lambda run: (_text(run.get("run_at") or run.get("timestamp") or run.get("started_at")), _text(run.get("run_id") or run.get("id"))))
        attempts = len(ordered)
        successes = sum(1 for run in ordered if _success(run))
        failures = attempts - successes
        timeouts = sum(1 for run in ordered if _text(run.get("error_type") or run.get("status")).lower() == "timeout")
        failure_rate = failures / attempts if attempts else 0.0
        severity = "critical" if failure_rate >= critical_failure_rate else ("warn" if failure_rate >= warning_failure_rate else "ok")
        rows.append({"source": source, "profile": profile, "attempts": attempts, "successes": successes, "failures": failures, "timeouts": timeouts, "success_rate": round(successes / attempts if attempts else 0.0, 4), "timeout_rate": round(timeouts / attempts if attempts else 0.0, 4), "consecutive_failures": _tail_failures(ordered), "severity": severity, "recommended_action": "Pause source and repair adapter." if severity == "critical" else ("Inspect recent failures." if severity == "warn" else "No action required.")})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["source"], row["profile"]))
    return {"schema_version": "max.signal_source_reliability_report.v1", "kind": "max.signal_source_reliability_report", "summary": {"source_profile_count": len(rows), "critical_count": sum(1 for row in rows if row["severity"] == "critical"), "warning_count": sum(1 for row in rows if row["severity"] == "warn")}, "rows": rows}


def _success(run: dict[str, Any]) -> bool:
    status = _text(run.get("status")).lower()
    return bool(run.get("success")) or status in {"success", "succeeded", "ok"}


def _tail_failures(runs: list[dict[str, Any]]) -> int:
    count = 0
    for run in reversed(runs):
        if _success(run):
            break
        count += 1
    return count


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
