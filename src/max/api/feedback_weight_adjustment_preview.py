"""JSON API renderer for feedback weight adjustment previews."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.feedback_weight_adjustment_preview.v1"
KIND = "max.api.feedback_weight_adjustment_preview"
STATUS_RANK = {"increased": 0, "decreased": 1, "unchanged": 2}


def feedback_weight_adjustment_preview_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    adjustments = _adjustments(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(adjustments),
        "adjustments": adjustments,
        "high_impact_adjustments": [row for row in adjustments if abs(row["delta"]) >= 0.1],
        "metadata": _metadata(payload, adjustments, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _adjustments(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("adjustments") if isinstance(payload.get("adjustments"), list) else payload.get("weight_adjustments")
    rows = [_adjustment(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -abs(row["delta"]), row["profile"], row["dimension"]))
    return rows


def _adjustment(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    current = _float(item.get("current_weight", item.get("current")))
    proposed = _float(item.get("proposed_weight", item.get("proposed")))
    delta = _float(item.get("delta")) if item.get("delta") is not None else round(proposed - current, 4)
    status = "increased" if delta > 0 else ("decreased" if delta < 0 else "unchanged")
    return {
        "dimension": _text(item.get("dimension")) or f"dimension-{index}",
        "current_weight": current,
        "proposed_weight": proposed,
        "delta": delta,
        "source_outcomes": _strings(item.get("source_outcomes") or item.get("outcomes")),
        "confidence": _score(item.get("confidence")),
        "profile": _text(item.get("profile")) or "unknown-profile",
        "status": status,
    }


def _summary(adjustments: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in adjustments)
    return {
        "adjustment_count": len(adjustments),
        "increased_count": counts["increased"],
        "decreased_count": counts["decreased"],
        "unchanged_count": counts["unchanged"],
        "total_absolute_delta": round(sum(abs(row["delta"]) for row in adjustments), 4),
    }


def _metadata(payload: Mapping[str, Any], adjustments: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "adjustment_count": len(adjustments)}


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    return sorted(str(item) for item in values if item not in (None, ""))


def _float(value: Any) -> float:
    try:
        return round(float(value or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _score(value: Any) -> float:
    try:
        return round(min(max(float(value or 0), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
