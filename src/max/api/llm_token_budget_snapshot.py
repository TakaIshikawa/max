"""JSON API renderer for LLM token budget snapshots."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.llm_token_budget_snapshot.v1"
KIND = "max.api.llm_token_budget_snapshot"


def llm_token_budget_snapshot_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    usage = _usage(payload)
    pricing = _pricing(payload)
    model_rows, unknown = _models(usage, pricing)
    total_cost = round(sum(row["estimated_cost"] for row in model_rows), 6)
    soft_limit = _money(payload.get("soft_limit", payload.get("soft_budget")))
    hard_limit = _money(payload.get("hard_limit", payload.get("hard_budget", payload.get("budget"))))
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(usage, total_cost, soft_limit, hard_limit),
        "model_usage": model_rows,
        "top_consumers": _top_consumers(usage, pricing),
        "unknown_cost_entries": unknown,
        "metadata": _metadata(payload, usage, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _usage(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("usage") if isinstance(payload.get("usage"), list) else payload.get("entries")
    rows = [_entry(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (-row["total_tokens"], row["consumer"], row["model"]))
    return rows


def _entry(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    prompt = _count(item.get("prompt_tokens", item.get("input_tokens")))
    completion = _count(item.get("completion_tokens", item.get("output_tokens")))
    return {
        "consumer": _text(item.get("consumer") or item.get("stage") or item.get("name")) or f"consumer-{index}",
        "model": _model(item.get("model") or item.get("model_name")),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _models(usage: list[dict[str, Any]], pricing: dict[str, dict[str, float]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    for row in usage:
        grouped[row["model"]]["prompt_tokens"] += row["prompt_tokens"]
        grouped[row["model"]]["completion_tokens"] += row["completion_tokens"]
        grouped[row["model"]]["total_tokens"] += row["total_tokens"]
    model_rows = []
    unknown = []
    for model, totals in grouped.items():
        price = pricing.get(model)
        if price is None:
            cost = 0.0
            unknown.append({"model": model, **totals})
        else:
            cost = (totals["prompt_tokens"] / 1000 * price["prompt"]) + (totals["completion_tokens"] / 1000 * price["completion"])
        model_rows.append({"model": model, **totals, "estimated_cost": round(cost, 6), "cost_known": price is not None})
    model_rows.sort(key=lambda row: (-row["estimated_cost"], row["model"]))
    unknown.sort(key=lambda row: row["model"])
    return model_rows, unknown


def _top_consumers(usage: list[dict[str, Any]], pricing: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    rows = []
    for row in usage:
        price = pricing.get(row["model"])
        cost = 0.0 if price is None else (row["prompt_tokens"] / 1000 * price["prompt"]) + (row["completion_tokens"] / 1000 * price["completion"])
        rows.append({**row, "estimated_cost": round(cost, 6), "cost_known": price is not None})
    rows.sort(key=lambda row: (-row["estimated_cost"], -row["total_tokens"], row["consumer"]))
    return rows[:5]


def _pricing(payload: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    raw = payload.get("pricing") if isinstance(payload.get("pricing"), Mapping) else payload.get("prices")
    prices: dict[str, dict[str, float]] = {}
    if isinstance(raw, Mapping):
        for model, value in raw.items():
            if isinstance(value, Mapping):
                prices[_model(model)] = {"prompt": _money(value.get("prompt", value.get("input", value.get("prompt_per_1k")))), "completion": _money(value.get("completion", value.get("output", value.get("completion_per_1k"))))}
            else:
                prices[_model(model)] = {"prompt": _money(value), "completion": _money(value)}
    return prices


def _summary(usage: list[dict[str, Any]], total_cost: float, soft_limit: float, hard_limit: float) -> dict[str, Any]:
    status = "within_budget"
    if hard_limit and total_cost >= hard_limit:
        status = "hard_limit_exceeded"
    elif soft_limit and total_cost >= soft_limit:
        status = "soft_limit_exceeded"
    limit = hard_limit or soft_limit
    return {
        "entry_count": len(usage),
        "prompt_tokens": sum(row["prompt_tokens"] for row in usage),
        "completion_tokens": sum(row["completion_tokens"] for row in usage),
        "total_tokens": sum(row["total_tokens"] for row in usage),
        "estimated_cost": total_cost,
        "remaining_budget": round(max(limit - total_cost, 0.0), 6) if limit else 0.0,
        "burn_percentage": round(total_cost / limit, 4) if limit else 0.0,
        "budget_status": status,
    }


def _metadata(payload: Mapping[str, Any], usage: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "entry_count": len(usage)}


def _model(value: Any) -> str:
    return (_text(value) or "unknown-model").lower().replace(" ", "-")


def _count(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _money(value: Any) -> float:
    try:
        return round(max(float(value or 0), 0.0), 6)
    except (TypeError, ValueError):
        return 0.0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
