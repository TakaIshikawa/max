"""JSON API renderer for LLM context window pressure status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.llm_context_window_pressure_status.v1"
KIND = "max.api.llm_context_window_pressure_status"


def llm_context_window_pressure_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "near_limit_requests": [row for row in rows if row["near_limit"]], "metadata": source_metadata(payload, request_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    threshold = max(0.0, float_or_zero(payload.get("near_limit_threshold") or 0.85))
    source = payload.get("requests") if isinstance(payload.get("requests"), list) else payload.get("items")
    rows = [_row(item, threshold) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["near_limit"], -row["pressure_ratio"], row["model"]))


def _row(item: Mapping[str, Any], threshold: float) -> dict[str, Any]:
    prompt = max(0, int_or_zero(item.get("prompt_tokens")))
    completion = max(0, int_or_zero(item.get("completion_tokens")))
    window = max(0, int_or_zero(item.get("context_window_tokens")))
    ratio = round((prompt + completion) / window, 4) if window else (1.0 if prompt + completion else 0.0)
    near = ratio >= threshold
    return {"model": _text(item.get("model")) or "unknown-model", "prompt_tokens": prompt, "completion_tokens": completion, "context_window_tokens": window, "pressure_ratio": ratio, "near_limit": near, "truncation_risk": _text(item.get("truncation_risk")) or ("high" if near else "low")}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "near_limit" if any(row["near_limit"] for row in rows) else "within_window", "request_count": len(rows), "near_limit_count": sum(1 for row in rows if row["near_limit"]), "max_pressure_ratio": max((row["pressure_ratio"] for row in rows), default=0.0), "truncation_risk_count": sum(1 for row in rows if row["truncation_risk"] not in ("", "low", "none"))}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
