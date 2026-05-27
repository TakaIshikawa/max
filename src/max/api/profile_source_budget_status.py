"""JSON API renderer for profile source budget status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.profile_source_budget_status.v1"
KIND = "max.api.profile_source_budget_status"
STATUS_RANK = {"exhausted": 0, "near_limit": 1, "available": 2}


def profile_source_budget_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    rows = _budgets(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "budgets": rows, "source_totals": _source_totals(rows), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, profile_count=len({row["profile"] for row in rows}))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _budgets(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("budgets") if isinstance(payload.get("budgets"), list) else payload.get("items")
    rows = [_budget(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["usage_ratio"], row["profile"], row["source"]))


def _budget(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    budget = max(0.0, float_or_zero(item.get("budget", item.get("limit", item.get("capacity")))))
    used = max(0.0, float_or_zero(item.get("used", item.get("usage", item.get("spent")))))
    remaining = max(budget - used, 0.0)
    ratio = round(min(used / budget, 1.0), 4) if budget else (1.0 if used else 0.0)
    status = "exhausted" if ratio >= 1.0 else ("near_limit" if ratio >= 0.8 else "available")
    return {"profile": _bucket(item.get("profile"), f"profile_{index}"), "source": _bucket(item.get("source") or item.get("source_id"), "unknown"), "budget": round(budget, 4), "used": round(used, 4), "remaining": round(remaining, 4), "usage_ratio": ratio, "budget_unit": _bucket(item.get("budget_unit") or item.get("unit"), "tokens"), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    status = "exhausted" if counts["exhausted"] else ("near_limit" if counts["near_limit"] else "available")
    return {"status": status, "profile_count": len({row["profile"] for row in rows}), "source_count": len({row["source"] for row in rows}), "exhausted_count": counts["exhausted"], "near_limit_count": counts["near_limit"]}


def _source_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = sorted({row["source"] for row in rows})
    return [{"source": source, "budget_count": sum(1 for row in rows if row["source"] == source), "used": round(sum(row["used"] for row in rows if row["source"] == source), 4)} for source in sources]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
