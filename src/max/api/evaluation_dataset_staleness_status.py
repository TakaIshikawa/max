"""JSON API renderer for evaluation dataset staleness status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.evaluation_dataset_staleness_status.v1"
KIND = "max.api.evaluation_dataset_staleness_status"
STATUS_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def evaluation_dataset_staleness_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = parse_datetime(as_of) if isinstance(as_of, str) else (as_of if isinstance(as_of, datetime) else None)
    datasets = _datasets(payload, now)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(datasets), "datasets": datasets, "status_totals": _status_totals(datasets), "metadata": source_metadata(payload, as_of=datetime_to_string(now) if isinstance(now, datetime) else as_of, dataset_count=len(datasets))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _datasets(payload: Mapping[str, Any], as_of: datetime | None) -> list[dict[str, Any]]:
    source = payload.get("datasets") if isinstance(payload.get("datasets"), list) else payload.get("evaluation_datasets")
    rows = [_dataset(item, index, as_of) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["age_days"], row["dataset_id"]))


def _dataset(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    age = max(0, int_or_zero(item.get("age_days"))) if item.get("age_days") is not None else _age_days(item.get("last_refreshed_at"), as_of)
    target = max(1, int_or_zero(item.get("target_refresh_days", item.get("refresh_days"))) or 30)
    status = _status(item.get("status"), age, target)
    return {"dataset_id": _text(item.get("dataset_id") or item.get("id")) or f"dataset-{index}", "profile": _bucket(item.get("profile"), "default"), "last_refreshed_at": datetime_to_string(parse_datetime(item.get("last_refreshed_at"))), "age_days": age, "target_refresh_days": target, "coverage_count": max(0, int_or_zero(item.get("coverage_count", item.get("coverage")))), "owner": _text(item.get("owner")) or "unassigned", "status": status}


def _age_days(value: Any, as_of: datetime | None) -> int:
    refreshed = parse_datetime(value)
    if refreshed is None or as_of is None:
        return 0
    current = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
    return max((current.astimezone(timezone.utc) - refreshed).days, 0)


def _status(value: Any, age: int, target: int) -> str:
    explicit = _bucket(value, "")
    if explicit in STATUS_RANK:
        return explicit
    if age >= target * 3:
        return "critical"
    if age > target:
        return "high"
    if age >= target:
        return "medium"
    return "low"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"status": "critical" if counts["critical"] else ("high" if counts["high"] else ("medium" if counts["medium"] else "low")), "dataset_count": len(rows), "stale_count": sum(1 for row in rows if row["status"] != "low"), "oldest_age_days": max((row["age_days"] for row in rows), default=0)}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "dataset_count": counts[status]} for status in ("critical", "high", "medium", "low")]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
