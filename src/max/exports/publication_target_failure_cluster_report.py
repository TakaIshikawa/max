"""Publication target failure cluster export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable

SCHEMA_VERSION = "max.publication_target_failure_cluster_report.v1"
KIND = "max.publication_target_failure_cluster_report"
DEFAULT_AS_OF = "2026-05-31"
SEVERITY_RANK = {"critical": 0, "warn": 1, "info": 2}


def generate_publication_target_failure_cluster_report(attempts: Iterable[dict[str, Any]], *, as_of: str = DEFAULT_AS_OF, repeated_failure_threshold: int = 3, stale_days_threshold: int = 7) -> dict[str, Any]:
    today = _date(as_of) or date(2026, 5, 31)
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in attempts:
        if _text(item.get("status")).lower() not in {"failed", "error", ""} and not item.get("failed"):
            continue
        key = (_text(item.get("target_type")) or "unknown", _text(item.get("target_name") or item.get("target")) or "unknown", _text(item.get("error_class") or item.get("error")) or "unknown_error", _text(item.get("profile")) or "default")
        groups[key].append(item)
    rows = []
    for (target_type, target_name, error_class, profile), items in groups.items():
        dates = [_date(item.get("failed_at") or item.get("created_at")) for item in items]
        dates = [value for value in dates if value]
        last_failure = max(dates) if dates else None
        oldest = min(dates) if dates else today
        age = max(0, (today - oldest).days)
        severity = "critical" if len(items) >= repeated_failure_threshold and age >= stale_days_threshold else ("warn" if len(items) >= repeated_failure_threshold or age >= stale_days_threshold else "info")
        rows.append({"target_type": target_type, "target_name": target_name, "error_class": error_class, "profile": profile, "failure_count": len(items), "last_failure_at": last_failure.isoformat() if last_failure else "", "oldest_failure_age_days": age, "sample_message": _text(items[0].get("message") or items[0].get("error_message")), "severity": severity, "recommendation": "Escalate target publisher repair." if severity == "critical" else "Triage publication failure cluster."})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["failure_count"], row["target_type"], row["target_name"], row["error_class"], row["profile"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"cluster_count": len(rows), "failed_attempt_count": sum(row["failure_count"] for row in rows)}, "rows": rows}


def render_publication_target_failure_cluster_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_publication_target_failure_cluster_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Publication Target Failure Cluster Report", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['target_type']} / {row['target_name']} / {row['profile']}: {row['failure_count']} {row['error_class']} failures ({row['severity']})")
    return "\n".join(lines).rstrip() + "\n"


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
