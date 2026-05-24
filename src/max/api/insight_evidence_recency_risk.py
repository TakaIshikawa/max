"""JSON API renderer for insight evidence recency risk."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.insight_evidence_recency_risk.v1"
KIND = "max.api.insight_evidence_recency_risk"
STATUS_RANK = {"expired": 0, "degraded": 1, "stale": 2, "current": 3}


def insight_evidence_recency_risk_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = _date(as_of) or _date(payload.get("as_of")) or datetime.now(timezone.utc)
    stale_days = _int(payload.get("stale_after_days", 30))
    expired_days = max(_int(payload.get("expired_after_days", 90)), stale_days)
    insights = _insights(payload, now, stale_days, expired_days)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(insights),
        "insights": insights,
        "evidence_age_buckets": _bucket_totals(insights),
        "highest_risk_insights": [row for row in insights if row["status"] in {"degraded", "expired"}],
        "profile_totals": _totals(insights, "profiles"),
        "category_totals": _totals(insights, "categories"),
        "metadata": _metadata(payload, insights, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _insights(payload: Mapping[str, Any], now: datetime, stale_days: int, expired_days: int) -> list[dict[str, Any]]:
    source = payload.get("insights") if isinstance(payload.get("insights"), list) else payload.get("items")
    rows = [_insight(item, index, now, stale_days, expired_days) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["insight_id"]))
    return rows


def _insight(item: Mapping[str, Any], index: int, now: datetime, stale_days: int, expired_days: int) -> dict[str, Any]:
    evidence = _evidence(item)
    buckets = [_bucket_age(ev.get("observed_at") or ev.get("timestamp") or ev.get("created_at"), now, stale_days, expired_days) for ev in evidence]
    counts = Counter(buckets)
    status = _status(counts, len(evidence))
    profiles = sorted({_bucket(ev.get("profile") or item.get("profile"), "unknown-profile") for ev in evidence}) or [_bucket(item.get("profile"), "unknown-profile")]
    categories = sorted({_bucket(ev.get("category") or item.get("category"), "unknown-category") for ev in evidence}) or [_bucket(item.get("category"), "unknown-category")]
    return {"insight_id": _text(item.get("insight_id") or item.get("id")) or f"insight-{index}", "title": _text(item.get("title")), "status": status, "evidence_count": len(evidence), "evidence_age_buckets": sorted(counts.items()), "profiles": profiles, "categories": categories}


def _status(counts: Counter[str], evidence_count: int) -> str:
    if evidence_count == 0:
        return "expired"
    if counts["expired"] == evidence_count:
        return "expired"
    if counts["expired"] and counts["fresh"]:
        return "degraded"
    if counts["expired"] or counts["stale"]:
        return "stale"
    return "current"


def _evidence(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else item.get("evidence_items")
    return [row for row in evidence if isinstance(row, Mapping)] if isinstance(evidence, list) else []


def _bucket_age(value: Any, now: datetime, stale_days: int, expired_days: int) -> str:
    parsed = _date(value)
    if parsed is None:
        return "unknown"
    days = max((now - parsed).days, 0)
    if days <= stale_days:
        return "fresh"
    if days <= expired_days:
        return "stale"
    return "expired"


def _summary(insights: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in insights)
    status = "expired" if counts["expired"] else ("degraded" if counts["degraded"] else ("stale" if counts["stale"] else "current"))
    return {"status": status, "insight_count": len(insights), "current_count": counts["current"], "stale_count": counts["stale"], "degraded_count": counts["degraded"], "expired_count": counts["expired"]}


def _bucket_totals(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in insights:
        counts.update({bucket: count for bucket, count in row["evidence_age_buckets"]})
    rows = [{"bucket": bucket, "count": count} for bucket, count in counts.items()]
    rows.sort(key=lambda row: row["bucket"])
    return rows


def _totals(insights: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    expired: Counter[str] = Counter()
    for row in insights:
        counts.update(row[field])
        if row["status"] in {"degraded", "expired"}:
            expired.update(row[field])
    rows = [{"bucket": bucket, "insight_count": count, "risk_count": expired[bucket]} for bucket, count in counts.items()]
    rows.sort(key=lambda row: (-row["risk_count"], row["bucket"]))
    return rows


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
