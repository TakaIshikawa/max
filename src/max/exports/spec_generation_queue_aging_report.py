"""Spec generation queue aging export report."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Iterable


def build_spec_generation_queue_aging_report(records: Iterable[Any], *, reference_time: str = "2026-05-27T00:00:00+00:00", sla_days: int = 7) -> dict[str, Any]:
    now = _dt(reference_time) or datetime(2026, 5, 27, tzinfo=timezone.utc)
    rows = []
    buckets = {"0-2d": 0, "3-7d": 0, "8-14d": 0, "15d+": 0}
    profile_breakdown: dict[str, int] = {}
    for raw in records:
        status = _norm(_get(raw, "status") or _get(raw, "idea_status"))
        has_spec = bool(_get(raw, "spec_id") or _get(raw, "generated_spec_id") or _get(raw, "published_at"))
        if status not in {"approved", "ready_for_spec", "queued"} or has_spec:
            continue
        approved_at = _dt(_get(raw, "approved_at") or _get(raw, "created_at")) or now
        age = max(0, (now - approved_at).days)
        bucket = _bucket(age)
        profile = _text(_get(raw, "profile")) or "unknown-profile"
        missing = [field for field in ("owner", "acceptance_criteria", "evidence_ids") if not _get(raw, field)]
        row = {"idea_id": _text(_get(raw, "idea_id") or _get(raw, "id")) or "unknown-idea", "profile": profile, "queued_days": age, "age_bucket": bucket, "missing_prerequisite_fields": missing, "sla_breached": age > sla_days}
        rows.append(row)
        buckets[bucket] += 1
        profile_breakdown[profile] = profile_breakdown.get(profile, 0) + 1
    rows.sort(key=lambda row: (-row["queued_days"], row["idea_id"].lower()))
    return {"schema_version": "max.spec_generation_queue_aging_report.v1", "kind": "max.spec_generation_queue_aging_report", "summary": {"queue_size": len(rows), "age_buckets": buckets, "profile_breakdown": dict(sorted(profile_breakdown.items())), "sla_breach_count": sum(1 for row in rows if row["sla_breached"])}, "oldest_queued_ideas": rows[:5], "queued_ideas": rows}


def render_spec_generation_queue_aging_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_spec_generation_queue_aging_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Spec Generation Queue Aging Report", "", "| Idea | Profile | Queued days | Bucket | Missing prerequisites | SLA breached |", "| --- | --- | ---: | --- | --- | --- |"]
    for row in report.get("queued_ideas", []):
        lines.append(f"| {row['idea_id']} | {row['profile']} | {row['queued_days']} | {row['age_bucket']} | {', '.join(row['missing_prerequisite_fields']) or 'none'} | {row['sla_breached']} |")
    return "\n".join(lines).rstrip() + "\n"


def _bucket(days: int) -> str:
    return "0-2d" if days <= 2 else "3-7d" if days <= 7 else "8-14d" if days <= 14 else "15d+"


def _get(raw: Any, key: str) -> Any:
    return raw.get(key) if isinstance(raw, dict) else getattr(raw, key, None)


def _dt(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _norm(value: Any) -> str:
    return _text(value).lower().replace(" ", "_").replace("-", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
