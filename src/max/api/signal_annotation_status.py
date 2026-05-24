"""JSON API renderer for signal annotation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "max.api.signal_annotation_status.v1"
KIND = "max.api.signal_annotation_status"


def signal_annotation_status_to_json(payload: Mapping[str, Any]) -> str:
    """Render signal annotation progress by source as deterministic API JSON."""
    sources = _sources(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(sources),
        "sources": sources,
        "metadata": _metadata(payload, sources),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _summary(sources: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(row["total_count"] for row in sources)
    annotated = sum(row["annotated_count"] for row in sources)
    unclassified = sum(row["unclassified_count"] for row in sources)
    return {
        "source_count": len(sources),
        "total_signals": total,
        "annotated_signals": annotated,
        "unclassified_signals": unclassified,
        "annotation_completion_percentage": _percentage(annotated, total),
    }


def _sources(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("sources")
    if not isinstance(source, list):
        source = payload.get("source_annotations")
    rows = [
        _source_row(item, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (-row["unclassified_count"], str(row["source"])))


def _source_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    total = _int_or_zero(item.get("total", item.get("total_count")))
    annotated = _int_or_zero(item.get("annotated", item.get("annotated_count")))
    return {
        "source": str(item.get("source") or item.get("name") or f"source-{index}"),
        "total_count": total,
        "annotated_count": annotated,
        "problem_count": _int_or_zero(item.get("problem", item.get("problem_count"))),
        "solution_count": _int_or_zero(item.get("solution", item.get("solution_count"))),
        "market_count": _int_or_zero(item.get("market", item.get("market_count"))),
        "unclassified_count": _int_or_zero(item.get("unclassified", item.get("unclassified_count"))),
        "annotation_completion_percentage": _percentage(annotated, total),
        "metadata": dict(_mapping(item.get("metadata"))),
    }


def _metadata(payload: Mapping[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version") or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "source_count": len(sources),
    }


def _percentage(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 2) if denominator else 0.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
