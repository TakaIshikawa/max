"""Insight evidence source concentration export report."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

SCHEMA_VERSION = "max.insight_evidence_source_concentration_report.v1"
KIND = "max.insight_evidence_source_concentration_report"


def generate_insight_evidence_source_concentration_report(records: Iterable[dict[str, Any]], *, threshold: float = 0.7) -> dict[str, Any]:
    distributions = []
    findings = []
    all_sources = set()
    for raw in records:
        insight_id = _text(raw.get("insight_id") or raw.get("id")) or "unknown-insight"
        sources = [_source(item) for item in raw.get("evidence", []) if _source(item)]
        counts = Counter(sources)
        all_sources.update(counts)
        total = sum(counts.values())
        dominant_source, dominant_count = counts.most_common(1)[0] if counts else ("unknown-source", 0)
        share = round(dominant_count / total, 4) if total else 0.0
        row = {"insight_id": insight_id, "source_counts": dict(sorted(counts.items())), "dominant_source": dominant_source, "dominant_source_share": share, "distinct_source_count": len(counts), "evidence_count": total}
        distributions.append(row)
        if total and (share > threshold or len(counts) == 1):
            findings.append({**row, "recommendation": "Add corroborating evidence from independent sources."})
    distributions.sort(key=lambda row: row["insight_id"].lower())
    findings.sort(key=lambda row: (-row["dominant_source_share"], row["insight_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_insights": len(distributions), "flagged_insights": len(findings), "distinct_sources": len(all_sources), "threshold": threshold}, "source_distributions": distributions, "findings": findings}


def _source(item: Any) -> str:
    if isinstance(item, dict):
        return _text(item.get("source") or item.get("source_id") or item.get("domain"))
    return _text(item)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

