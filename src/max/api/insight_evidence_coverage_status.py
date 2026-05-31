"""JSON API renderer for insight evidence coverage status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, source_metadata

SCHEMA_VERSION = "max.api.insight_evidence_coverage_status.v1"
KIND = "max.api.insight_evidence_coverage_status"


def insight_evidence_coverage_status_to_json(
    payload: Mapping[str, Any],
    *,
    min_evidence_count: int | None = None,
    min_source_count: int | None = None,
) -> str:
    min_evidence = _int(min_evidence_count if min_evidence_count is not None else payload.get("min_evidence_count"), 2)
    min_sources = _int(min_source_count if min_source_count is not None else payload.get("min_source_count"), 2)
    rows = [_row(item, min_evidence, min_sources) for item in _items(payload)]
    rows.sort(key=lambda row: (row["severity_rank"], row["evidence_count"], row["insight_id"]))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows, min_evidence, min_sources), "rows": rows, "metadata": source_metadata(payload, insight_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    source = payload.get("insights") if isinstance(payload.get("insights"), list) else payload.get("items")
    return [item for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []


def _row(item: Mapping[str, Any], min_evidence: int, min_sources: int) -> dict[str, Any]:
    evidence = as_list(item.get("evidence_ids") or item.get("evidence") or item.get("evidence_count"))
    evidence_count = _int(item.get("evidence_count"), len(evidence)) if not isinstance(item.get("evidence_count"), list) else len(evidence)
    sources = {_source(value) for value in as_list(item.get("source_names") or item.get("sources") or item.get("source_ids")) if _source(value)}
    missing = bool(item.get("missing_evidence_chain") or item.get("missing_evidence") or item.get("missing_evidence_chains"))
    severity = "critical" if missing else "warn" if evidence_count < min_evidence or len(sources) < min_sources else "healthy"
    return {"insight_id": str(item.get("insight_id") or item.get("id") or "unknown_insight"), "evidence_count": evidence_count, "source_count": len(sources), "missing_evidence_chain": missing, "severity": severity, "severity_rank": {"critical": 0, "warn": 1, "healthy": 2}[severity]}


def _summary(rows: list[dict[str, Any]], min_evidence: int, min_sources: int) -> dict[str, Any]:
    total = len(rows)
    return {"total_insights": total, "under_supported_count": sum(1 for row in rows if row["severity"] in {"critical", "warn"}), "missing_evidence_count": sum(1 for row in rows if row["missing_evidence_chain"]), "average_evidence_count": round(sum(row["evidence_count"] for row in rows) / total, 4) if total else 0.0, "min_evidence_count": min_evidence, "min_source_count": min_sources}


def _source(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("source") or value.get("name") or value.get("source_id")
    return " ".join(str(value).strip().split()) if value not in (None, "") else ""


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
