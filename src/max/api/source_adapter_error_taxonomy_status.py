"""JSON API renderer for source adapter error taxonomy status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_error_taxonomy_status.v1"
KIND = "max.api.source_adapter_error_taxonomy_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}
KNOWN = {"auth", "rate_limit", "parse", "timeout", "unknown"}


def source_adapter_error_taxonomy_status_to_json(payload: Mapping[str, Any], *, total_error_threshold: int = 10, dominant_share_threshold: float = 0.75) -> str:
    rows = [_row(item, index, total_error_threshold, dominant_share_threshold) for index, item in enumerate(_items(payload), start=1)]
    rows = sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["total_errors"], row["source"], row["adapter"]))
    aggregates = Counter()
    for row in rows:
        aggregates.update(row["error_counts"])
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"adapter_count": len(rows), "erroring_adapters": sum(1 for row in rows if row["total_errors"] > 0), "critical_adapters": sum(1 for row in rows if row["status"] == "critical"), "dominant_error_categories": dict(sorted(aggregates.items()))}, "adapter_rows": rows, "metadata": source_metadata(payload, adapter_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("adapters") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, threshold: int, dominant_threshold: float) -> dict[str, Any]:
    counts = _counts(item.get("error_counts"))
    total = max(sum(counts.values()), max(0, int_or_zero(item.get("total_errors"))))
    category, count = max(counts.items(), key=lambda pair: (pair[1], pair[0]), default=("unknown", 0))
    share = count / total if total else 0.0
    status = "critical" if total >= threshold and share >= dominant_threshold else "warning" if total > 0 else "ok"
    return {"source": _text(item.get("source")) or f"source-{index}", "adapter": _text(item.get("adapter")) or _text(item.get("source")) or "unknown", "error_counts": counts, "total_errors": total, "dominant_error_category": category if total else None, "dominant_error_share": round(share, 4), "last_error_at": _text(item.get("last_error_at")) or None, "status": status}


def _counts(value: Any) -> dict[str, int]:
    counts = {category: 0 for category in sorted(KNOWN)}
    if isinstance(value, Mapping):
        for key, raw in value.items():
            category = _category(key)
            counts[category] = counts.get(category, 0) + max(0, int_or_zero(raw))
    return {key: count for key, count in sorted(counts.items()) if count or key == "unknown"}


def _category(value: Any) -> str:
    text = _text(value).casefold().replace("-", "_").replace(" ", "_")
    return text if text in KNOWN else "unknown"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
