"""JSON API renderer for signal ingestion lag status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.signal_ingestion_lag_status.v1"
KIND = "max.api.signal_ingestion_lag_status"
STATUS_RANK = {"missing": 0, "stale": 1, "fresh": 2}


def signal_ingestion_lag_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "status_buckets": dict(Counter(row["status"] for row in rows)), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, source_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("sources") if isinstance(payload.get("sources"), list) else payload.get("items")
    rows = [_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["source"]))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    lag = max(0.0, float_or_zero(item.get("lag_minutes")))
    threshold = max(0.0, float_or_zero(item.get("stale_threshold_minutes")))
    missing = not item.get("newest_signal_at") or not item.get("fetched_at")
    status = "missing" if missing else ("stale" if threshold and lag > threshold else "fresh")
    return {"source": _text(item.get("source")) or f"source-{index}", "newest_signal_at": _text(item.get("newest_signal_at")) or None, "fetched_at": _text(item.get("fetched_at")) or None, "lag_minutes": round(lag, 4), "stale_threshold_minutes": round(threshold, 4), "signal_count": max(0, int_or_zero(item.get("signal_count"))), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    max_lag = max((row["lag_minutes"] for row in rows), default=0.0)
    return {"status": "missing" if counts["missing"] else ("stale" if counts["stale"] else "fresh"), "total_sources": len(rows), "stale_sources": counts["stale"], "missing_sources": counts["missing"], "max_lag_minutes": max_lag}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
