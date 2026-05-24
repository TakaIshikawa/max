"""JSON API renderer for evaluation dimension drift."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.evaluation_dimension_drift.v1"
KIND = "max.api.evaluation_dimension_drift"
STATUS_RANK = {"regressed": 0, "drifting": 1, "stable": 2}


def evaluation_dimension_drift_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    threshold = _number(payload.get("drift_threshold", 0.05))
    regression = _number(payload.get("regression_threshold", threshold))
    dimensions = _dimensions(payload, threshold, regression)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(dimensions),
        "dimensions": dimensions,
        "affected_profiles": _affected_profiles(dimensions),
        "largest_regressions": [row for row in dimensions if row["status"] == "regressed"][:5],
        "metadata": _metadata(payload, dimensions, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _dimensions(payload: Mapping[str, Any], threshold: float, regression: float) -> list[dict[str, Any]]:
    source = payload.get("dimensions") if isinstance(payload.get("dimensions"), list) else payload.get("averages")
    rows = [_dimension(item, index, threshold, regression) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["delta"], row["dimension"]))
    return rows


def _dimension(item: Mapping[str, Any], index: int, threshold: float, regression: float) -> dict[str, Any]:
    current = _number(item.get("current_average", item.get("current")))
    baseline = _number(item.get("baseline_average", item.get("baseline")))
    delta = round(current - baseline, 4)
    status = "regressed" if delta <= -abs(regression) else ("drifting" if abs(delta) >= threshold else "stable")
    return {"dimension": _text(item.get("dimension") or item.get("name")) or f"dimension-{index}", "profile": _bucket(item.get("profile"), "unknown-profile"), "current_average": current, "baseline_average": baseline, "delta": delta, "status": status}


def _summary(dimensions: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in dimensions)
    status = "regressed" if counts["regressed"] else ("drifting" if counts["drifting"] else "stable")
    return {"status": status, "dimension_count": len(dimensions), "stable_count": counts["stable"], "drifting_count": counts["drifting"], "regressed_count": counts["regressed"]}


def _affected_profiles(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter(row["profile"] for row in dimensions if row["status"] != "stable")
    rows = [{"profile": profile, "affected_dimension_count": count} for profile, count in counts.items()]
    rows.sort(key=lambda row: (-row["affected_dimension_count"], row["profile"]))
    return rows


def _metadata(payload: Mapping[str, Any], dimensions: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "dimension_count": len(dimensions)}


def _number(value: Any) -> float:
    try:
        return round(float(value or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
