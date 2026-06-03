"""JSON API renderer for insight evidence recency skew status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.insight_evidence_recency_skew_status.v1"
KIND = "max.api.insight_evidence_recency_skew_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def insight_evidence_recency_skew_status_to_json(payload: Mapping[str, Any], *, warning_days: int = 14, critical_days: int = 30, now: str | datetime | None = None) -> str:
    as_of = parse_datetime(now) or datetime.now(timezone.utc)
    rows = _rows(payload, warning_days, critical_days, as_of)
    worst = max(rows, key=lambda row: (row["oldest_age_days"], row["age_spread_days"], row["insight_id"]), default=None)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_insights": len(rows), "critical_insights": sum(1 for row in rows if row["status"] == "critical"), "warning_insights": sum(1 for row in rows if row["status"] == "warning"), "max_age_spread_days": max((row["age_spread_days"] for row in rows), default=0), "oldest_evidence_insight": worst["insight_id"] if worst else None}, "insight_rows": rows, "metadata": source_metadata(payload, insight_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warning: int, critical: int, as_of: datetime) -> list[dict[str, Any]]:
    source = payload.get("insights") or payload.get("items") or payload
    if isinstance(source, Mapping):
        items = [{**dict(value), "insight_id": value.get("insight_id") or key} for key, value in source.items() if isinstance(value, Mapping)]
    elif isinstance(source, list):
        items = [item for item in source if isinstance(item, Mapping)]
    else:
        items = []
    rows = [_row(item, index, warning, critical, as_of) for index, item in enumerate(items, start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["oldest_age_days"], -row["age_spread_days"], row["insight_id"]))


def _row(item: Mapping[str, Any], index: int, warning: int, critical: int, as_of: datetime) -> dict[str, Any]:
    ages: list[int] = []
    malformed = 0
    evidence = item.get("evidence") or item.get("evidence_items") or item.get("signals") or []
    if isinstance(evidence, Mapping):
        evidence = list(evidence.values())
    for evidence_item in evidence if isinstance(evidence, list) else []:
        value = evidence_item.get("published_at") or evidence_item.get("timestamp") or evidence_item.get("created_at") if isinstance(evidence_item, Mapping) else evidence_item
        parsed = parse_datetime(value)
        if parsed is None:
            malformed += 1
            continue
        ages.append(max((as_of - parsed).days, 0))
    newest = min(ages) if ages else 0
    oldest = max(ages) if ages else 0
    spread = oldest - newest
    status = "critical" if oldest >= critical or spread >= critical else "warning" if oldest >= warning or spread >= warning else "ok"
    return {"insight_id": _text(item.get("insight_id") or item.get("id")) or f"insight-{index}", "evidence_count": len(ages), "newest_age_days": newest, "oldest_age_days": oldest, "age_spread_days": spread, "malformed_timestamps": malformed, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
