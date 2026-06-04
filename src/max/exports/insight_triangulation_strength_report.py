"""Insight triangulation strength export report."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_insight_triangulation_strength_report(records: Iterable[dict[str, Any]], *, minimum_sources: int = 3) -> dict[str, Any]:
    rows = []
    all_sources: set[str] = set()
    for index, record in enumerate(records, start=1):
        insight_id = _text(record.get("insight_id") or record.get("id")) or f"insight-{index}"
        evidence = record.get("evidence") if isinstance(record.get("evidence"), list) else []
        sources = sorted({_text(item.get("source") or item.get("source_id")) for item in evidence if isinstance(item, dict) and _text(item.get("source") or item.get("source_id"))})
        all_sources.update(sources)
        source_count = len(sources)
        strength = round(min(source_count / max(1, minimum_sources), 1.0), 4)
        severity = "critical" if source_count == 0 else ("warn" if source_count < minimum_sources else "ok")
        rows.append({"insight_id": insight_id, "source_count": source_count, "sources": sources, "triangulation_strength": strength, "severity": severity})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["source_count"], row["insight_id"]))
    severity_counts = Counter(row["severity"] for row in rows)
    return {"schema_version": "max.insight_triangulation_strength_report.v1", "kind": "max.insight_triangulation_strength_report", "summary": {"total_insights": len(rows), "weak_insights": severity_counts["critical"] + severity_counts["warn"], "distinct_sources": len(all_sources)}, "rows": rows}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
