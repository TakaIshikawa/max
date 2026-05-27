"""JSON API renderer for insight to unit conversion status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import as_list, datetime_to_string, int_or_zero, source_metadata, strings

SCHEMA_VERSION = "max.api.insight_to_unit_conversion_status.v1"
KIND = "max.api.insight_to_unit_conversion_status"
STATUS_RANK = {"blocked": 0, "partial": 1, "converted": 2, "pending": 3}


def insight_to_unit_conversion_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    insights = _insights(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(insights), "insights": insights, "blocked_insights": [row for row in insights if row["status"] == "blocked"], "profile_domain_counts": _profile_domain_counts(insights), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, insight_count=len(insights))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _insights(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("insights") if isinstance(payload.get("insights"), list) else payload.get("items")
    rows = [_insight(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["domain"], row["insight_id"]))


def _insight(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    unit_count = max(0, int_or_zero(item.get("unit_count", item.get("converted_units", item.get("buildable_unit_count")))))
    reason = _bucket(item.get("blocker_reason") or item.get("blocked_reason") or item.get("reason"), "")
    missing = strings(item.get("missing_inputs", item.get("missing")))
    status = _bucket(item.get("status"), "")
    if status not in STATUS_RANK:
        status = "blocked" if reason or missing else ("converted" if unit_count else "pending")
    return {"insight_id": _text(item.get("insight_id") or item.get("id")) or f"insight-{index}", "profile": _bucket(item.get("profile"), "default"), "domain": _bucket(item.get("domain"), "general"), "unit_count": unit_count, "converted": status == "converted" or unit_count > 0, "blocker_reason": reason, "missing_inputs": missing, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    converted = sum(1 for row in rows if row["converted"])
    blocked = sum(1 for row in rows if row["status"] == "blocked")
    rate = round(converted / len(rows), 4) if rows else 0.0
    status = "blocked" if blocked else ("healthy" if rate >= 0.8 or not rows else "partial")
    return {"status": status, "insight_count": len(rows), "converted_count": converted, "blocked_count": blocked, "conversion_rate": rate}


def _profile_domain_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter((row["profile"], row["domain"]) for row in rows)
    return [{"profile": p, "domain": d, "insight_count": c} for (p, d), c in sorted(counts.items())]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
