"""Insight evidence source diversity export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.insight_evidence_source_diversity_report.v1"
KIND = "max.insight_evidence_source_diversity_report"


def generate_insight_evidence_source_diversity_report(records: Iterable[dict[str, Any]], *, min_distinct_sources: int = 2) -> dict[str, Any]:
    rows = []
    for index, raw in enumerate(records):
        evidence = _items(raw.get("evidence") or raw.get("evidence_items") or raw.get("citations"))
        explicit_sources = [_text(item) for item in _items(raw.get("sources"))]
        sources = sorted({source for source in explicit_sources + [_source(item) for item in evidence] if source})
        evidence_count = _int(raw.get("evidence_count")) or len(evidence)
        distinct_source_count = len(sources)
        rows.append(
            {
                "insight_id": _text(raw.get("insight_id") or raw.get("id")) or f"insight-{index + 1}",
                "evidence_count": evidence_count,
                "distinct_source_count": distinct_source_count,
                "sources": sources,
                "status": "diverse" if distinct_source_count >= min_distinct_sources else "needs_more_sources",
            }
        )
    rows.sort(key=lambda row: (row["status"] != "needs_more_sources", row["insight_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"insight_count": len(rows), "flagged_count": sum(1 for row in rows if row["status"] == "needs_more_sources"), "min_distinct_sources": min_distinct_sources}, "rows": rows}


def _source(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("source") or value.get("source_name") or value.get("adapter"))
    return _text(value)


def _items(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
