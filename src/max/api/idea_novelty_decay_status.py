"""JSON API renderer for idea novelty decay status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.idea_novelty_decay_status.v1"
KIND = "max.api.idea_novelty_decay_status"


def idea_novelty_decay_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(rows),
        "rows": rows,
        "stale_ideas": [row for row in rows if row["stale"]],
        "metadata": source_metadata(payload, idea_count=len(rows)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    default_threshold = float_or_zero(payload.get("decay_threshold") or 0.75)
    source = payload.get("ideas") if isinstance(payload.get("ideas"), list) else payload.get("items")
    rows = [
        _row(item, default_threshold, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (not row["stale"], -row["similarity_score"], row["idea_id"]))


def _row(item: Mapping[str, Any], default_threshold: float, index: int) -> dict[str, Any]:
    threshold = round(max(0.0, float_or_zero(item.get("decay_threshold") or default_threshold)), 4)
    similarity = round(max(0.0, float_or_zero(item.get("similarity_score"))), 4)
    stale = similarity >= threshold
    return {
        "idea_id": _text(item.get("idea_id")) or f"idea-{index}",
        "profile": _bucket(item.get("profile"), "unknown_profile"),
        "generated_at": _text(item.get("generated_at")) or None,
        "last_similar_seen_at": _text(item.get("last_similar_seen_at")) or None,
        "similarity_score": similarity,
        "decay_threshold": threshold,
        "stale": stale,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    stale_count = sum(1 for row in rows if row["stale"])
    return {
        "status": "stale_ideas" if stale_count else "fresh",
        "idea_count": len(rows),
        "stale_count": stale_count,
        "max_similarity_score": max((row["similarity_score"] for row in rows), default=0.0),
    }


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
