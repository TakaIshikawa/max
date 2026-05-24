"""JSON API renderer for insight evidence coverage."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.insight_evidence_coverage.v1"
KIND = "max.api.insight_evidence_coverage"


def insight_evidence_coverage_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = _date(as_of) or _date(payload.get("as_of")) or datetime.now(timezone.utc)
    stale_days = _int(payload.get("stale_after_days", payload.get("stale_cutoff_days", 30)))
    min_sources = _int(payload.get("min_source_count", payload.get("min_sources", 2)))
    min_evidence = _int(payload.get("min_evidence_count", payload.get("min_evidence", 2)))
    insights = _insights(payload, now, stale_days, min_sources, min_evidence)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(insights),
        "insights": insights,
        "coverage": {
            "sources": _totals(insights, "sources"),
            "categories": _totals(insights, "categories"),
            "profiles": _totals(insights, "profiles"),
            "recency_buckets": _recency_totals(insights),
        },
        "weak_evidence_insights": [row for row in insights if row["weak_evidence"]],
        "single_source_warnings": [row for row in insights if row["source_count"] == 1],
        "stale_evidence_warnings": [row for row in insights if row["stale_evidence"]],
        "suggested_evidence_collection_actions": _actions(insights),
        "metadata": _metadata(payload, insights, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _insights(payload: Mapping[str, Any], now: datetime, stale_days: int, min_sources: int, min_evidence: int) -> list[dict[str, Any]]:
    source = payload.get("insights") if isinstance(payload.get("insights"), list) else payload.get("items")
    rows = [_insight(item, index, now, stale_days, min_sources, min_evidence) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (not row["weak_evidence"], row["insight_id"]))
    return rows


def _insight(item: Mapping[str, Any], index: int, now: datetime, stale_days: int, min_sources: int, min_evidence: int) -> dict[str, Any]:
    evidence = _evidence(item)
    sources = sorted({_bucket(row.get("source") or row.get("source_name"), "unknown-source") for row in evidence})
    categories = sorted({_bucket(row.get("category") or item.get("category"), "unknown-category") for row in evidence}) or [_bucket(item.get("category"), "unknown-category")]
    profiles = sorted({_bucket(row.get("profile") or item.get("profile"), "unknown-profile") for row in evidence}) or [_bucket(item.get("profile"), "unknown-profile")]
    recencies = [_recency(row.get("observed_at") or row.get("created_at") or row.get("timestamp"), now, stale_days) for row in evidence]
    stale = bool(evidence) and all(bucket == "stale" for bucket in recencies)
    evidence_count = len(evidence)
    weak = evidence_count < min_evidence or len(sources) < min_sources or stale
    return {
        "insight_id": _text(item.get("insight_id") or item.get("id")) or f"insight-{index}",
        "title": _text(item.get("title")),
        "evidence_count": evidence_count,
        "source_count": len(sources),
        "sources": sources,
        "categories": categories,
        "profiles": profiles,
        "recency_buckets": sorted(Counter(recencies).items()),
        "weak_evidence": weak,
        "stale_evidence": stale,
    }


def _evidence(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else item.get("evidence_items")
    return [row for row in evidence if isinstance(row, Mapping)] if isinstance(evidence, list) else []


def _totals(insights: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in insights:
        counts.update(row[field])
    rows = [{"bucket": bucket, "count": count} for bucket, count in counts.items()]
    rows.sort(key=lambda row: (-row["count"], row["bucket"]))
    return rows


def _recency_totals(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in insights:
        counts.update({bucket: count for bucket, count in row["recency_buckets"]})
    rows = [{"bucket": bucket, "count": count} for bucket, count in counts.items()]
    rows.sort(key=lambda row: row["bucket"])
    return rows


def _actions(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in insights:
        if row["source_count"] <= 1:
            rows.append({"insight_id": row["insight_id"], "action": "Collect evidence from an additional source", "current_sources": row["sources"]})
        if row["stale_evidence"]:
            rows.append({"insight_id": row["insight_id"], "action": "Refresh stale evidence before publication"})
        if row["evidence_count"] == 0:
            rows.append({"insight_id": row["insight_id"], "action": "Attach category evidence", "categories": row["categories"]})
    return rows


def _summary(insights: list[dict[str, Any]]) -> dict[str, Any]:
    return {"insight_count": len(insights), "weak_evidence_count": sum(1 for row in insights if row["weak_evidence"]), "single_source_count": sum(1 for row in insights if row["source_count"] == 1), "stale_evidence_count": sum(1 for row in insights if row["stale_evidence"])}


def _recency(value: Any, now: datetime, stale_days: int) -> str:
    parsed = _date(value)
    if parsed is None:
        return "unknown"
    days = (now - parsed).days
    if days <= 7:
        return "fresh"
    if days <= stale_days:
        return "aging"
    return "stale"


def _metadata(payload: Mapping[str, Any], insights: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "insight_count": len(insights)}


def _date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
