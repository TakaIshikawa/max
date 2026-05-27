"""JSON API renderer for gap detection coverage status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.gap_detection_coverage_status.v1"
KIND = "max.api.gap_detection_coverage_status"


def gap_detection_coverage_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "undercovered_groups": [row for row in rows if row["undercovered"]], "metadata": source_metadata(payload, group_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("groups") if isinstance(payload.get("groups"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["undercovered"], row["profile"], row["domain"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    detected = max(0, int_or_zero(item.get("detected_gaps")))
    addressed = max(0, int_or_zero(item.get("addressed_gaps")))
    target = max(0.0, float_or_zero(item.get("target_coverage_ratio")))
    ratio = round(addressed / detected, 4) if detected else 1.0
    return {"profile": _bucket(item.get("profile"), "default"), "domain": _bucket(item.get("domain"), "general"), "detected_gaps": detected, "addressed_gaps": addressed, "ignored_gaps": max(0, int_or_zero(item.get("ignored_gaps"))), "last_detection_at": _text(item.get("last_detection_at")) or None, "target_coverage_ratio": round(target, 4), "coverage_ratio": ratio, "undercovered": bool(detected and ratio < target)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "undercovered" if any(row["undercovered"] for row in rows) else "covered", "total_detected_gaps": sum(row["detected_gaps"] for row in rows), "total_addressed_gaps": sum(row["addressed_gaps"] for row in rows), "undercovered_count": sum(1 for row in rows if row["undercovered"])}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
