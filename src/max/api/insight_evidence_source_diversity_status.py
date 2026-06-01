"""JSON API renderer for insight evidence source diversity status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.insight_evidence_source_diversity_status.v1"
KIND = "max.api.insight_evidence_source_diversity_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def insight_evidence_source_diversity_status_to_json(payload: Mapping[str, Any], *, as_of: datetime | str | None = None) -> str:
    checked_at = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    minimum = max(1, int_or_zero(payload.get("minimum_sources") or payload.get("min_sources") or 2))
    max_share = float_or_zero(payload.get("max_dominant_share") or 0.7) or 0.7
    rows = [_insight(insight, minimum, max_share) for insight in _insights(payload)]
    rows = sorted(rows, key=lambda row: (RANK[row["risk_level"]], row["insight_id"].casefold()))
    under = sum(1 for row in rows if "insufficient_sources" in row["risk_reasons"])
    concentrated = sum(1 for row in rows if "dominant_source_concentration" in row["risk_reasons"])
    status = "warning" if under or concentrated else "healthy"
    weakest = rows[0]["insight_id"] if rows and rows[0]["risk_level"] != "healthy" else None
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": _stamp(checked_at), "status": status, "summary": {"status": status, "insight_count": len(rows), "under_diversified_count": under, "concentrated_count": concentrated, "weakest_insight": weakest}, "insights": rows, "risky_insights": [row for row in rows if row["risk_level"] != "healthy"], "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _insights(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for insight in list_of_maps(payload.get("insights")):
        evidence = list_of_maps(insight.get("evidence") or insight.get("sources"))
        if evidence:
            grouped[_text(insight.get("insight_id") or insight.get("id")) or "insight"].extend(evidence)
    for row in list_of_maps(payload.get("evidence") or payload.get("rows") or payload.get("items")):
        grouped[_text(row.get("insight_id") or row.get("insight")) or "insight"].append(row)
    return [{"insight_id": key, "evidence": value} for key, value in grouped.items()]


def _insight(item: Mapping[str, Any], minimum: int, max_share: float) -> dict[str, Any]:
    sources = [_text(row.get("source") or row.get("source_id") or row.get("publisher")) or "unknown" for row in list_of_maps(item.get("evidence"))]
    counts = dict(sorted(Counter(sources).items()))
    total = sum(counts.values())
    unique = len(counts)
    dominant = max(counts.values()) / total if total else 0.0
    reasons = []
    if unique < minimum:
        reasons.append("insufficient_sources")
    if dominant > max_share and total:
        reasons.append("dominant_source_concentration")
    risk = "critical" if len(reasons) == 2 else ("warning" if reasons else "healthy")
    return {"insight_id": _text(item.get("insight_id")) or "insight", "evidence_count": total, "unique_source_count": unique, "dominant_source_share": round(dominant, 4), "source_counts": counts, "risk_reasons": reasons, "risk_level": risk}


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
