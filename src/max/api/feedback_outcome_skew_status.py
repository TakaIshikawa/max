"""JSON API renderer for feedback outcome skew status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.feedback_outcome_skew_status.v1"
KIND = "max.api.feedback_outcome_skew_status"


def feedback_outcome_skew_status_to_json(payload: Mapping[str, Any]) -> str:
    items = list_of_maps(payload.get("feedback") or payload.get("outcomes"))
    min_samples = int(payload.get("min_sample_size", 10))
    imbalance = float(payload.get("imbalance_threshold", 0.7))
    distribution = _distribution(items)
    max_share = max((row["percentage"] for row in distribution), default=0.0) / 100
    status = "insufficient_data" if len(items) < min_samples else ("critical" if max_share >= imbalance else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "sample_count": len(items)}, "outcome_distribution": distribution, "reviewer_skew": _group(items, "reviewer"), "profile_skew": _group(items, "profile"), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _distribution(items: list[Mapping[str, object]]) -> list[dict[str, object]]:
    counts = Counter(_bucket(item.get("outcome"), "skipped") for item in items)
    total = sum(counts.values())
    rows = []
    for outcome in ("approved", "rejected", "skipped"):
        count = counts[outcome]
        rows.append({"outcome": outcome, "count": count, "percentage": round((count / total * 100) if total else 0.0, 2)})
    if rows and total:
        rows[-1]["percentage"] = round(100.0 - sum(float(row["percentage"]) for row in rows[:-1]), 2)
    return rows


def _group(items: list[Mapping[str, object]], field: str) -> list[dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for item in items:
        grouped[_bucket(item.get(field), "unknown")].append(item)
    rows = [{field: key, "sample_count": len(values), "outcomes": _distribution(values)} for key, values in grouped.items()]
    return sorted(rows, key=lambda row: str(row[field]))


def _bucket(value: object, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
