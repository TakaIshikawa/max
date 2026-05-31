"""Signal annotation gap export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable

SCHEMA_VERSION = "max.signal_annotation_gap_report.v1"
KIND = "max.signal_annotation_gap_report"
DEFAULT_AS_OF = "2026-05-31"
REQUIRED_FIELDS = ("role", "market", "problem", "solution")
SEVERITY_RANK = {"critical": 0, "warn": 1, "info": 2}


def generate_signal_annotation_gap_report(signals: Iterable[dict[str, Any]], *, as_of: str = DEFAULT_AS_OF, warn_age_days: int = 7, critical_age_days: int = 30) -> dict[str, Any]:
    today = _date(as_of) or date(2026, 5, 31)
    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {"signal_count": 0, "missing_fields": defaultdict(int), "oldest_age_days": 0})
    for signal in signals:
        missing = [field for field in REQUIRED_FIELDS if not _text(signal.get(field))]
        if not missing:
            continue
        age = max(0, (today - (_date(signal.get("created_at") or signal.get("observed_at")) or today)).days)
        bucket = "30d+" if age >= 30 else ("7-29d" if age >= 7 else "0-6d")
        key = (_text(signal.get("source")) or "unknown", _text(signal.get("profile")) or "default", bucket)
        group = groups[key]
        group["signal_count"] += 1
        group["oldest_age_days"] = max(group["oldest_age_days"], age)
        for field in missing:
            group["missing_fields"][field] += 1
    rows = []
    for (source, profile, bucket), group in groups.items():
        oldest = group["oldest_age_days"]
        severity = "critical" if oldest >= critical_age_days else ("warn" if oldest >= warn_age_days else "info")
        rows.append({"source": source, "profile": profile, "age_bucket": bucket, "signal_count": group["signal_count"], "oldest_age_days": oldest, "missing_fields": dict(sorted(group["missing_fields"].items())), "severity": severity, "next_action": "Prioritize annotation backfill for stale signals." if severity != "info" else "Queue for normal annotation review."})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["source"], row["profile"], row["age_bucket"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"gap_group_count": len(rows), "gap_signal_count": sum(row["signal_count"] for row in rows)}, "rows": rows}


def render_signal_annotation_gap_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_signal_annotation_gap_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Signal Annotation Gap Report", ""]
    for row in report.get("rows") or []:
        fields = ", ".join(f"{name}:{count}" for name, count in row["missing_fields"].items())
        lines.append(f"- {row['source']} / {row['profile']} / {row['age_bucket']}: {row['signal_count']} signals, {fields}. {row['next_action']}")
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
