"""JSON API renderer for LLM context truncation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.llm_context_truncation_status.v1"
KIND = "max.api.llm_context_truncation_status"
STATUS_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def llm_context_truncation_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _rate(payload.get("warning_truncation_rate"), 0.05)
    critical = _rate(payload.get("critical_truncation_rate"), 0.2)
    rows = [_row(item, index, warning, critical) for index, item in enumerate(list_of_maps(payload.get("prompts") or payload.get("rows") or payload.get("truncations")), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["truncation_rate"], row["prompt_id"]))
    models = sorted({row["model"] for row in rows})
    by_model = [{"model": model, "affected_prompt_count": sum(1 for row in rows if row["model"] == model and row["truncated_tokens"] > 0)} for model in models]
    affected = [row for row in rows if row["truncated_tokens"] > 0]
    status = "no_data" if not rows else ("critical" if any(row["status"] == "critical" for row in rows) else ("warning" if any(row["status"] == "warning" for row in rows) else "healthy"))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "prompt_count": len(rows), "affected_prompt_count": len(affected), "worst_model": affected[0]["model"] if affected else None}, "prompts": rows, "affected_by_model": by_model, "highest_loss_prompt": affected[0] if affected else None, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    input_tokens = max(0, int_or_zero(item.get("input_tokens", item.get("tokens"))))
    token_limit = max(0, int_or_zero(item.get("token_limit", item.get("limit"))))
    truncated = max(0, int_or_zero(item.get("truncated_tokens", item.get("lost_tokens"))))
    rate = round(truncated / input_tokens, 4) if input_tokens else 0.0
    status = "critical" if rate >= critical and truncated > 0 else ("warning" if rate >= warning and truncated > 0 else "healthy")
    return {"prompt_id": str(item.get("prompt_id") or item.get("id") or f"prompt-{index}"), "model": str(item.get("model") or "unknown_model"), "input_tokens": input_tokens, "token_limit": token_limit, "truncated_tokens": truncated, "truncation_rate": rate, "status": status}


def _rate(value: Any, default: float) -> float:
    try:
        return max(0.0, float(value if value is not None else default))
    except (TypeError, ValueError):
        return default
