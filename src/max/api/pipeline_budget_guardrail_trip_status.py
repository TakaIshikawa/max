"""JSON API renderer for pipeline budget guardrail trip status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.pipeline_budget_guardrail_trip_status.v1"
KIND = "max.api.pipeline_budget_guardrail_trip_status"
LEVEL_RANK = {"hard": 0, "soft": 1}


def pipeline_budget_guardrail_trip_status_to_json(payload: Mapping[str, Any]) -> str:
    breaches = _breaches(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(breaches), "breaches": breaches, "metadata": source_metadata(payload, breach_count=len(breaches))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _breaches(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("breaches") if isinstance(payload.get("breaches"), list) else payload.get("trips")
    rows = [_breach(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (LEVEL_RANK.get(row["level"], 2), -row["overage"], row["stage"]))


def _breach(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    limit = float_or_zero(item.get("limit", item.get("budget")))
    observed = float_or_zero(item.get("observed_usage", item.get("observed", item.get("usage"))))
    level = _text(item.get("level") or item.get("severity")).lower()
    if level not in LEVEL_RANK:
        level = "hard" if limit and observed >= limit else "soft"
    overage = max(observed - limit, 0.0)
    return {"stage": _text(item.get("stage")) or f"stage-{index}", "dimension": _text(item.get("dimension") or item.get("unit")) or "tokens", "level": level, "limit": round(limit, 4), "observed_usage": round(observed, 4), "overage": round(overage, 4), "recommended_action": _text(item.get("recommended_action")) or ("Stop stage and resize budget." if level == "hard" else "Review burn rate before continuing.")}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"breach_count": len(rows), "soft_count": sum(1 for row in rows if row["level"] == "soft"), "hard_count": sum(1 for row in rows if row["level"] == "hard"), "severity": "critical" if any(row["level"] == "hard" for row in rows) else ("warn" if rows else "ok")}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
