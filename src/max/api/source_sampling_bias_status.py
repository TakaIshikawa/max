"""JSON API renderer for source sampling bias status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_sampling_bias_status.v1"
KIND = "max.api.source_sampling_bias_status"


def source_sampling_bias_status_to_json(payload: Mapping[str, Any]) -> str:
    threshold = max(0.0, float_or_zero(payload.get("bias_threshold") or payload.get("share_delta_threshold") or 0.1))
    rows = _rows(payload, threshold)
    biased = [row for row in rows if row["biased"]]
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "biased" if biased else "balanced", "source_count": len(rows), "biased_source_count": len(biased), "max_abs_share_delta": max((row["abs_share_delta"] for row in rows), default=0.0)}, "rows": rows, "biased_sources": biased, "metadata": source_metadata(payload, bias_threshold=threshold)}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], threshold: float) -> list[dict[str, Any]]:
    items = list_of_maps(payload.get("sources") or payload.get("items"))
    total = sum(max(0, int_or_zero(item.get("sample_count") or item.get("count"))) for item in items)
    rows = [_row(item, total, threshold) for item in items]
    rows.sort(key=lambda row: (not row["biased"], -row["abs_share_delta"], row["source"], row["profile"]))
    return rows


def _row(item: Mapping[str, Any], total: int, threshold: float) -> dict[str, Any]:
    count = max(0, int_or_zero(item.get("sample_count") or item.get("count")))
    actual = round(count / total, 4) if total else 0.0
    expected = max(0.0, float_or_zero(item.get("expected_share") or item.get("target_share")))
    delta = round(actual - expected, 4)
    biased = abs(delta) > threshold
    return {"source": _bucket(item.get("source") or item.get("id"), "unknown_source"), "profile": _bucket(item.get("profile"), "default"), "sample_count": count, "actual_share": actual, "expected_share": expected, "share_delta": delta, "abs_share_delta": abs(delta), "biased": biased, "severity": "warning" if biased else "ok"}


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
