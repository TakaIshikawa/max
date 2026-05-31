"""Feedback recency decay export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable

SCHEMA_VERSION = "max.feedback_recency_decay_report.v1"
KIND = "max.feedback_recency_decay_report"
DEFAULT_AS_OF = "2026-05-31"
SEVERITY_RANK = {"critical": 0, "warn": 1, "info": 2}


def generate_feedback_recency_decay_report(feedback: Iterable[dict[str, Any]], *, as_of: str = DEFAULT_AS_OF, stale_days: int = 30, expired_days: int = 90, high_weight_threshold: float = 0.7) -> dict[str, Any]:
    today = _date(as_of) or date(2026, 5, 31)
    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {"record_count": 0, "oldest_feedback_age_days": 0, "max_weight": 0.0})
    for item in feedback:
        age = max(0, (today - (_date(item.get("last_seen_at") or item.get("seen_at")) or today)).days)
        bucket = "expired" if age >= expired_days else ("stale" if age >= stale_days else "fresh")
        key = (_text(item.get("profile")) or "default", _text(item.get("outcome_label") or item.get("label")) or "unlabeled", bucket)
        group = groups[key]
        group["record_count"] += 1
        group["oldest_feedback_age_days"] = max(group["oldest_feedback_age_days"], age)
        group["max_weight"] = max(group["max_weight"], _float(item.get("weight"), 1.0))
    rows = []
    for (profile, label, bucket), group in groups.items():
        severity = "critical" if bucket == "expired" and group["max_weight"] >= high_weight_threshold else ("warn" if bucket in {"expired", "stale"} else "info")
        rows.append({"profile": profile, "outcome_label": label, "decay_bucket": bucket, "record_count": group["record_count"], "oldest_feedback_age_days": group["oldest_feedback_age_days"], "max_weight": round(group["max_weight"], 4), "severity": severity, "recommended_action": "Refresh or downweight stale high-impact feedback." if severity == "critical" else ("Review feedback decay weights." if severity == "warn" else "No refresh required.")})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["profile"], row["outcome_label"], row["decay_bucket"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"bucket_count": len(rows), "stale_or_expired_count": sum(row["record_count"] for row in rows if row["decay_bucket"] != "fresh")}, "rows": rows}


def render_feedback_recency_decay_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_feedback_recency_decay_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Feedback Recency Decay Report", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['profile']} / {row['outcome_label']} / {row['decay_bucket']}: {row['record_count']} records, oldest {row['oldest_feedback_age_days']}d. {row['recommended_action']}")
    return "\n".join(lines).rstrip() + "\n"


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
