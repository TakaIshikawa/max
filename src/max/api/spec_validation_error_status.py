"""JSON API renderer for spec validation error status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import source_metadata

SCHEMA_VERSION = "max.api.spec_validation_error_status.v1"
KIND = "max.api.spec_validation_error_status"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def spec_validation_error_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "severity_counts": _counts(rows, "severity"), "error_code_counts": _counts(rows, "error_code"), "metadata": source_metadata(payload, error_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("errors") if isinstance(payload.get("errors"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (SEVERITY_RANK.get(row["severity"], 9), row["spec_id"], row["field"], row["error_code"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    return {"spec_id": _text(item.get("spec_id")) or "unknown", "profile": _bucket(item.get("profile"), "default"), "field": _text(item.get("field")) or "unknown", "error_code": _bucket(item.get("error_code"), "unknown"), "severity": _bucket(item.get("severity"), "info"), "first_seen_at": _text(item.get("first_seen_at")) or None}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    codes = Counter(row["error_code"] for row in rows)
    return {"status": "critical" if any(row["severity"] == "critical" for row in rows) else ("errors" if rows else "clean"), "affected_specs": len({row["spec_id"] for row in rows}), "total_errors": len(rows), "critical_errors": sum(1 for row in rows if row["severity"] == "critical"), "top_error_codes": [{"error_code": key, "count": count} for key, count in codes.most_common(5)]}


def _counts(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(row[field] for row in rows).items()))


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
