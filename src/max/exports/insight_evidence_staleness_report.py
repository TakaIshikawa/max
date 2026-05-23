"""Insight evidence staleness export report."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.insight_evidence_staleness_report.v1"
KIND = "max.insight_evidence_staleness_report"
DEFAULT_AS_OF = "2026-05-20"


class InsightEvidenceStalenessInput(TypedDict, total=False):
    insight_id: str
    source: str
    evidence_id: str
    evidence_timestamp: str
    timestamp: str
    owner: str
    refresh_threshold_days: int | float | str


def build_insight_evidence_staleness_report(
    records: Iterable[InsightEvidenceStalenessInput | dict[str, Any]],
    *,
    title: str = "Insight Evidence Staleness Report",
    as_of: str = DEFAULT_AS_OF,
    stale_after_days: int = 30,
) -> dict[str, Any]:
    rows = _normalize_records(records, as_of=as_of, stale_after_days=stale_after_days)
    refresh_needed = [row for row in rows if row["refresh_needed"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Insight Evidence Staleness Report",
        "as_of": _text(as_of) or DEFAULT_AS_OF,
        "summary": {
            "evidence_count": len(rows),
            "refresh_needed_count": len(refresh_needed),
            "missing_timestamp_count": sum(1 for row in rows if row["bucket"] == "missing"),
        },
        "freshness_buckets": _bucket_totals(rows),
        "source_totals": _source_totals(rows),
        "refresh_needed": sorted(refresh_needed, key=lambda row: (-row["age_days"], row["source"].lower(), row["insight_id"].lower())),
        "evidence": rows,
    }


def render_insight_evidence_staleness_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Insight Evidence Staleness Report'}",
        "",
        "## Summary",
        "",
        f"- Evidence records: {summary.get('evidence_count', 0)}",
        f"- Refresh needed: {summary.get('refresh_needed_count', 0)}",
        f"- Missing timestamps: {summary.get('missing_timestamp_count', 0)}",
        "",
        "## Stale Insight Details",
        "",
    ]
    stale = report.get("refresh_needed") or []
    if not stale:
        lines.append("- No stale insight evidence found.")
    else:
        for row in stale:
            lines.append(f"- {row['insight_id']} from {row['source']}: {row['bucket']} ({row['age_days']} days)")
    lines.extend(["", "## Source Totals", ""])
    for row in report.get("source_totals") or []:
        lines.append(f"- {row['source']}: {row['evidence_count']} records, {row['refresh_needed_count']} refresh needed")
    return "\n".join(lines).rstrip() + "\n"


def render_insight_evidence_staleness_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[InsightEvidenceStalenessInput | dict[str, Any]], *, as_of: str, stale_after_days: int) -> list[dict[str, Any]]:
    as_of_date = _date(as_of) or _date(DEFAULT_AS_OF) or date(2026, 5, 20)
    rows = []
    for index, raw in enumerate(records):
        timestamp = _text(raw.get("evidence_timestamp") or raw.get("timestamp"))
        evidence_date = _date(timestamp)
        age = (as_of_date - evidence_date).days if evidence_date else 0
        threshold = _int(raw.get("refresh_threshold_days"), stale_after_days)
        bucket = _bucket(age, bool(evidence_date), threshold)
        rows.append(
            {
                "insight_id": _text(raw.get("insight_id")) or f"unknown-insight-{index + 1}",
                "evidence_id": _text(raw.get("evidence_id")) or f"evidence-{index + 1}",
                "source": _text(raw.get("source")) or "Unspecified source",
                "owner": _text(raw.get("owner")) or "Unassigned",
                "evidence_timestamp": timestamp,
                "age_days": max(age, 0),
                "bucket": bucket,
                "refresh_threshold_days": threshold,
                "refresh_needed": bucket in {"stale", "critical", "missing"},
            }
        )
    rows.sort(key=lambda row: (row["source"].lower(), row["insight_id"].lower(), row["evidence_id"].lower()))
    return rows


def _bucket(age: int, has_date: bool, threshold: int) -> str:
    if not has_date:
        return "missing"
    if age > threshold * 2:
        return "critical"
    if age > threshold:
        return "stale"
    return "fresh"


def _bucket_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"bucket": bucket, "count": sum(1 for row in rows if row["bucket"] == bucket)} for bucket in ("fresh", "stale", "critical", "missing")]


def _source_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = sorted({row["source"] for row in rows}, key=str.lower)
    return [{"source": source, "evidence_count": sum(1 for row in rows if row["source"] == source), "refresh_needed_count": sum(1 for row in rows if row["source"] == source and row["refresh_needed"])} for source in sources]


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).date()
        except ValueError:
            return None


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
