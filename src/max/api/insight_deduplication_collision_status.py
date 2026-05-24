"""JSON API renderer for insight deduplication collision status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import as_list, datetime_to_string, float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.insight_deduplication_collision_status.v1"
KIND = "max.api.insight_deduplication_collision_status"
STATUS_RANK = {"collision": 0, "needs_review": 1, "safe_review": 2}


def insight_deduplication_collision_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    candidates = _candidates(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(candidates), "candidates": candidates, "collisions": [row for row in candidates if row["status"] == "collision"], "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, candidate_count=len(candidates))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _candidates(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("candidates") if isinstance(payload.get("candidates"), list) else payload.get("merge_candidates")
    rows = [_candidate(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["confidence_delta"], row["candidate_id"]))


def _candidate(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    labels = _strings(item.get("labels", item.get("conflicting_labels")))
    conflict = _bool(item.get("conflict", item.get("label_conflict"))) or len(labels) > 1
    delta = _ratio(item.get("confidence_delta", item.get("delta")))
    overlap = _ratio(item.get("evidence_overlap", item.get("overlap_ratio")))
    status = "collision" if conflict and (delta >= 0.25 or overlap < 0.5) else ("needs_review" if conflict or delta >= 0.15 or overlap < 0.7 else "safe_review")
    return {"candidate_id": _text(item.get("candidate_id") or item.get("id")) or f"candidate-{index}", "primary_insight_id": _text(item.get("primary_insight_id") or item.get("source_id")) or f"insight-{index}", "merge_insight_id": _text(item.get("merge_insight_id") or item.get("target_id")) or f"merge-{index}", "labels": labels, "conflicting_labels": conflict, "confidence_delta": delta, "evidence_overlap": overlap, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"candidate_count": len(rows), "safe_review_count": counts["safe_review"], "needs_review_count": counts["needs_review"], "collision_count": counts["collision"]}


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _ratio(value: Any) -> float:
    return round(min(max(float_or_zero(value), 0.0), 1.0), 4)


def _strings(value: Any) -> list[str]:
    return sorted({_text(item) for item in as_list(value) if _text(item)})


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

