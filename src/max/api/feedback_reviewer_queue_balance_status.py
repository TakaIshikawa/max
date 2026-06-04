"""JSON API renderer for feedback reviewer queue balance status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.feedback_reviewer_queue_balance_status.v1"
KIND = "max.api.feedback_reviewer_queue_balance_status"


def feedback_reviewer_queue_balance_status_to_json(records: Any, *, overload_threshold: int = 5) -> str:
    payload = mapping(records)
    source = payload.get("feedback") or payload.get("records") or payload.get("items") or (records if isinstance(records, list) else [])
    counts = Counter(_text(item.get("reviewer_id") or item.get("reviewer")) or "unassigned" for item in list_of_maps(source) if _open(item))
    rows = [{"reviewer_id": reviewer, "open_count": count, "status": "overloaded" if count > overload_threshold else "ok"} for reviewer, count in counts.items()]
    rows.sort(key=lambda row: (-row["open_count"], row["reviewer_id"]))
    total = sum(counts.values())
    max_queue = max(counts.values(), default=0)
    min_queue = min(counts.values(), default=0)
    imbalance = round(max_queue / min_queue, 4) if min_queue else (float(max_queue) if max_queue else 0.0)
    overloaded = [row["reviewer_id"] for row in rows if row["status"] == "overloaded"]
    status = "warning" if overloaded or imbalance > 2 else "ok"
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": status, "summary": {"total_open": total, "max_queue": max_queue, "min_queue": min_queue, "imbalance_ratio": imbalance, "overloaded_reviewers": overloaded, "status": status}, "reviewers": rows, "metadata": source_metadata(payload, reviewer_count=len(rows))}, indent=2, sort_keys=True)


def _open(item: Mapping[str, Any]) -> bool:
    return (_text(item.get("status") or item.get("state")) or "open").casefold() not in {"closed", "resolved", "done"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
