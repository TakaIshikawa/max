"""Insight attribution completeness export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.insight_attribution_completeness_report.v1"
KIND = "max.insight_attribution_completeness_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class InsightAttributionInput(TypedDict, total=False):
    insight_id: str
    title: str
    evidence_signal_ids: list[str] | str
    evidence_sources: list[str] | str
    owner: str


def build_insight_attribution_completeness_report(
    records: Iterable[InsightAttributionInput | dict[str, Any]],
    *,
    minimum_evidence_count: int = 2,
    minimum_unique_sources: int = 2,
    title: str = "Insight Attribution Completeness Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    min_evidence = max(0, int(minimum_evidence_count))
    min_sources = max(0, int(minimum_unique_sources))
    rows = [_row(raw, index, min_evidence, min_sources) for index, raw in enumerate(records, start=1)]
    rows.sort(key=lambda row: (row["status"] == "complete", -row["missing_evidence_count"], -row["missing_source_count"], row["insight_id"].lower()))
    incomplete = [row for row in rows if row["status"] == "incomplete"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Insight Attribution Completeness Report",
        "thresholds": {"minimum_evidence_count": min_evidence, "minimum_unique_sources": min_sources},
        "summary": {
            "total_insights": len(rows),
            "incomplete_insights": len(incomplete),
            "average_evidence_count": round(sum(row["evidence_count"] for row in rows) / len(rows), 2) if rows else 0.0,
            "lowest_source_diversity": min([row["unique_source_count"] for row in rows] or [0]),
        },
        "insight_attribution": rows,
        "incomplete_attribution": incomplete,
    }


def render_insight_attribution_completeness_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_insight_attribution_completeness_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Insight Attribution Completeness Report'}",
        "",
        "## Summary",
        "",
        f"- Insights: {summary.get('total_insights', 0)}",
        f"- Incomplete: {summary.get('incomplete_insights', 0)}",
        "",
        "## Incomplete Attribution",
        "",
    ]
    incomplete = report.get("incomplete_attribution") or []
    if incomplete:
        for row in incomplete:
            lines.append(f"- {row['insight_id']}: missing {row['missing_evidence_count']} evidence and {row['missing_source_count']} sources")
    else:
        lines.append("- No incomplete insight attribution.")
    return "\n".join(lines).rstrip() + "\n"


def _row(raw: dict[str, Any], index: int, min_evidence: int, min_sources: int) -> dict[str, Any]:
    evidence = _list(raw.get("evidence_signal_ids") or raw.get("signal_ids") or raw.get("evidence_ids"))
    sources = _ordered(_list(raw.get("evidence_sources") or raw.get("sources") or raw.get("source_adapters")))
    missing_evidence = max(0, min_evidence - len(evidence))
    missing_sources = max(0, min_sources - len(sources))
    return {
        "insight_id": _text(raw.get("insight_id") or raw.get("id")) or f"unknown-insight-{index}",
        "title": _text(raw.get("title")) or "Untitled insight",
        "owner": _text(raw.get("owner")) or "Unassigned",
        "evidence_signal_ids": evidence,
        "evidence_sources": sources,
        "evidence_count": len(evidence),
        "unique_source_count": len(sources),
        "missing_evidence_count": missing_evidence,
        "missing_source_count": missing_sources,
        "status": "complete" if missing_evidence == 0 and missing_sources == 0 else "incomplete",
    }


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, tuple | set):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [item.strip() for item in text.split(",") if item.strip()] if text else []


def _ordered(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=str.casefold)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
