"""JSON API renderer for LLM prompt token waste status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.llm_prompt_token_waste_status.v1"
KIND = "max.api.llm_prompt_token_waste_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def llm_prompt_token_waste_status_to_json(payload: Mapping[str, Any], *, low_utilization: float = 0.25, failure_rate_threshold: float = 0.2) -> str:
    rows = [_row(item, index, low_utilization, failure_rate_threshold) for index, item in enumerate(_items(payload), start=1)]
    rows = sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["wasted_context_tokens"], row["prompt_name"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"prompt_count": len(rows), "wasteful_prompts": sum(1 for row in rows if row["status"] != "ok"), "critical_prompts": sum(1 for row in rows if row["status"] == "critical"), "total_wasted_context_tokens": sum(row["wasted_context_tokens"] for row in rows)}, "prompt_rows": rows, "metadata": source_metadata(payload, prompt_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("prompts") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, low_utilization: float, failure_threshold: float) -> dict[str, Any]:
    input_tokens = _non_negative(item.get("input_tokens"))
    output_tokens = _non_negative(item.get("output_tokens"))
    max_context = _non_negative(item.get("max_context_tokens"))
    failures = _non_negative(item.get("failure_count"))
    runs = _non_negative(item.get("run_count"))
    used = input_tokens + output_tokens
    utilization = used / max_context if max_context else 0.0
    failure_rate = failures / runs if runs else 0.0
    wasted = max(max_context - used, 0)
    status = "critical" if failure_rate >= failure_threshold and failures else "warning" if max_context and utilization <= low_utilization else "ok"
    return {"prompt_name": _text(item.get("prompt_name") or item.get("name")) or f"prompt-{index}", "model": _text(item.get("model")) or None, "input_tokens": input_tokens, "output_tokens": output_tokens, "max_context_tokens": max_context, "utilization": round(utilization, 4), "wasted_context_tokens": wasted, "failure_count": failures, "run_count": runs, "failure_rate": round(failure_rate, 4), "status": status}


def _non_negative(value: Any) -> int:
    return max(0, int_or_zero(value))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
