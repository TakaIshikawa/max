"""JSON API renderer for spec generation failure taxonomy status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import bool_or_default, datetime_to_string, source_metadata, strings

SCHEMA_VERSION = "max.api.spec_generation_failure_taxonomy_status.v1"
KIND = "max.api.spec_generation_failure_taxonomy_status"
CATEGORIES = {"missing_evidence", "invalid_stack", "budget_exceeded", "template_error", "unknown"}


def spec_generation_failure_taxonomy_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    failures = _failures(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(failures), "failures": failures, "categories": _categories(failures), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, failure_count=len(failures))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _failures(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("failures") if isinstance(payload.get("failures"), list) else payload.get("items")
    rows = [_failure(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (row["category"], row["idea_id"], row["attempt_id"]))


def _failure(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    category = _bucket(item.get("cause") or item.get("category") or item.get("failure_type"), "unknown")
    if category not in CATEGORIES:
        category = "unknown"
    retryable = bool_or_default(item.get("retryable"), default=category in {"missing_evidence", "budget_exceeded", "template_error"})
    return {"attempt_id": _text(item.get("attempt_id") or item.get("id")) or f"attempt-{index}", "idea_id": _text(item.get("idea_id")) or "unknown-idea", "category": category, "retryable": retryable, "message": _text(item.get("message") or item.get("error")), "affected_idea_ids": strings(item.get("affected_idea_ids", item.get("idea_ids", item.get("idea_id"))))}


def _categories(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids: defaultdict[str, set[str]] = defaultdict(set)
    for row in rows:
        ids[row["category"]].update(row["affected_idea_ids"])
    counts = Counter(row["category"] for row in rows)
    return [{"category": category, "failure_count": counts[category], "affected_idea_ids": sorted(ids[category])} for category in sorted(CATEGORIES)]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["category"] for row in rows)
    retryable = sum(1 for row in rows if row["retryable"])
    top = counts.most_common(1)[0][0] if counts else None
    return {"status": "blocked" if rows else "healthy", "failure_count": len(rows), "retryable_count": retryable, "non_retryable_count": len(rows) - retryable, "top_category": top}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
