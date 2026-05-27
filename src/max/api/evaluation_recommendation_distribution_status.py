"""JSON API renderer for evaluation recommendation distribution status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.evaluation_recommendation_distribution_status.v1"
KIND = "max.api.evaluation_recommendation_distribution_status"


def evaluation_recommendation_distribution_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    rows = _evaluations(payload)
    distributions = _distributions(rows, payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows, distributions), "distributions": distributions, "evaluations": rows, "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, evaluation_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _evaluations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("evaluations") if isinstance(payload.get("evaluations"), list) else payload.get("items")
    rows = []
    for index, item in enumerate(source if isinstance(source, list) else [], start=1):
        if isinstance(item, Mapping):
            rows.append({"idea_id": _text(item.get("idea_id") or item.get("id")) or f"idea-{index}", "profile": _bucket(item.get("profile"), "default"), "evaluator": _bucket(item.get("evaluator") or item.get("evaluator_id"), "unknown"), "recommendation": _bucket(item.get("recommendation") or item.get("decision"), "review")})
    return sorted(rows, key=lambda row: (row["profile"], row["evaluator"], row["idea_id"]))


def _distributions(rows: list[dict[str, Any]], payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_min = _ratio(payload.get("expected_min", 0.0))
    expected_max = _ratio(payload.get("expected_max", 1.0))
    groups = sorted({(row["profile"], row["evaluator"]) for row in rows})
    result = []
    for profile, evaluator in groups:
        group = [row for row in rows if row["profile"] == profile and row["evaluator"] == evaluator]
        counts = Counter(row["recommendation"] for row in group)
        for recommendation in ("approve", "review", "reject", "defer"):
            ratio = round(counts[recommendation] / len(group), 4) if group else 0.0
            skewed = ratio < expected_min or ratio > expected_max
            result.append({"profile": profile, "evaluator": evaluator, "recommendation": recommendation, "count": counts[recommendation], "ratio": ratio, "skewed": skewed})
    return sorted(result, key=lambda row: (not row["skewed"], row["profile"], row["evaluator"], row["recommendation"]))


def _summary(rows: list[dict[str, Any]], distributions: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["recommendation"] for row in rows)
    skewed = sum(1 for row in distributions if row["skewed"])
    return {"status": "skewed" if skewed else "balanced", "evaluation_count": len(rows), "recommendation_counts": {key: counts[key] for key in ("approve", "review", "reject", "defer")}, "skewed_bucket_count": skewed}


def _ratio(value: Any) -> float:
    return round(min(max(float_or_zero(value), 0.0), 1.0), 4)


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
