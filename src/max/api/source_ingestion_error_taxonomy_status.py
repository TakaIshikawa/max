"""JSON API renderer for source ingestion error taxonomy status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.source_ingestion_error_taxonomy_status.v1"
KIND = "max.api.source_ingestion_error_taxonomy_status"
STATUS_RANK = {"failing": 0, "noisy": 1, "clean": 2}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


def source_ingestion_error_taxonomy_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    errors = _errors(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(errors), "errors": errors, "adapter_totals": _totals(errors, "adapter"), "category_totals": _totals(errors, "category"), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, error_count=len(errors))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _errors(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("errors") if isinstance(payload.get("errors"), list) else payload.get("ingestion_errors")
    rows = [_error(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], SEVERITY_RANK[row["severity"]], row["adapter"], row["category"]))


def _error(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    severity = _severity(item.get("severity"))
    retryable = _bool(item.get("retryable", item.get("can_retry")))
    count = max(0, int_or_zero(item.get("count", item.get("occurrences", 1)))) or 1
    status = "failing" if not retryable or severity in {"critical", "high"} else "noisy"
    return {"id": _text(item.get("id")) or f"error-{index}", "adapter": _text(item.get("adapter") or item.get("adapter_name")) or "unknown-adapter", "category": _text(item.get("category") or item.get("error_type")) or "unknown", "severity": severity, "retryable": retryable, "count": count, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    overall = "failing" if counts["failing"] else ("noisy" if rows else "clean")
    return {"status": overall, "error_count": len(rows), "total_occurrences": sum(row["count"] for row in rows), "retryable_count": sum(row["count"] for row in rows if row["retryable"]), "non_retryable_count": sum(row["count"] for row in rows if not row["retryable"]), "failing_count": counts["failing"], "noisy_count": counts["noisy"]}


def _totals(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row[field]].append(row)
    output = [{"status": "failing" if any(item["status"] == "failing" for item in items) else "noisy", field: value, "error_count": len(items), "retryable_count": sum(item["count"] for item in items if item["retryable"]), "non_retryable_count": sum(item["count"] for item in items if not item["retryable"])} for value, items in grouped.items()]
    return sorted(output, key=lambda row: (STATUS_RANK[row["status"]], row[field]))


def _severity(value: Any) -> str:
    severity = _text(value).lower()
    return severity if severity in SEVERITY_RANK else "unknown"


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "retryable"}
    return bool(value)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

