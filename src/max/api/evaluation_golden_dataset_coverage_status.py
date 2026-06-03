"""JSON API renderer for evaluation golden dataset coverage status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.evaluation_golden_dataset_coverage_status.v1"
KIND = "max.api.evaluation_golden_dataset_coverage_status"


def evaluation_golden_dataset_coverage_status_to_json(payload: Mapping[str, Any]) -> str:
    stale_days = max(0, int_or_zero(payload.get("stale_days"))) or 90
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    goldens = [_golden(row, stale_days, as_of) for row in _items(payload)]
    goldens.sort(key=lambda row: (_rank(row["status"]), row["profile"], row["dimension"]))
    summary = _summary(goldens)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "goldens": goldens, "metadata": source_metadata(payload, golden_set_count=len(goldens))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("goldens")) or list_of_maps(payload.get("items")) or list_of_maps(payload.get("rows"))


def _golden(row: Mapping[str, Any], stale_days: int, as_of: datetime) -> dict[str, Any]:
    count = max(0, int_or_zero(row.get("golden_count")))
    minimum = max(0, int_or_zero(row.get("min_required")))
    coverage = round(count / minimum, 4) if minimum else 1.0
    updated = parse_datetime(row.get("last_updated_at"))
    age_days = max((as_of - updated).days, 0) if updated else None
    under = minimum > 0 and count < minimum
    stale = age_days is not None and age_days > stale_days
    status = "critical" if under and stale else "warning" if under or stale else "ok"
    return {"dimension": _bucket(row.get("dimension"), "unknown_dimension"), "profile": _bucket(row.get("profile"), "unknown_profile"), "golden_count": count, "min_required": minimum, "coverage": coverage, "last_updated_at": row.get("last_updated_at"), "age_days": age_days, "undercovered": under, "stale": stale, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    under = sum(1 for row in rows if row["undercovered"])
    stale = sum(1 for row in rows if row["stale"])
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "golden_set_count": len(rows), "undercovered_count": under, "stale_count": stale, "critical_count": critical}


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
