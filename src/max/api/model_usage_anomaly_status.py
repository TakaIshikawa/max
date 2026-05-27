"""JSON API renderer for model usage anomaly status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.model_usage_anomaly_status.v1"
KIND = "max.api.model_usage_anomaly_status"
STATUS_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def model_usage_anomaly_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    models = _models(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(models), "models": models, "status_totals": _status_totals(models), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, model_count=len(models))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _models(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("models") if isinstance(payload.get("models"), list) else payload.get("usage")
    rows = [_model(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -abs(row["current_cost_usd"] - row["baseline_cost_usd"]), row["model"], row["profile"]))


def _model(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    current_tokens = max(0, int_or_zero(item.get("current_tokens", item.get("tokens"))))
    baseline_tokens = max(0, int_or_zero(item.get("baseline_tokens")))
    current_cost = max(0.0, round(float_or_zero(item.get("current_cost_usd", item.get("cost_usd"))), 4))
    baseline_cost = max(0.0, round(float_or_zero(item.get("baseline_cost_usd")), 4))
    baseline_missing = baseline_tokens <= 0 and baseline_cost <= 0
    delta_ratio = _delta_ratio(item.get("delta_ratio"), current_tokens, baseline_tokens, current_cost, baseline_cost)
    status = _status(item.get("status"), delta_ratio, baseline_missing)
    return {"model": _text(item.get("model")) or f"model-{index}", "profile": _bucket(item.get("profile"), "default"), "current_tokens": current_tokens, "baseline_tokens": baseline_tokens, "delta_ratio": delta_ratio, "current_cost_usd": current_cost, "baseline_cost_usd": baseline_cost, "baseline_missing": baseline_missing, "status": status}


def _delta_ratio(value: Any, current_tokens: int, baseline_tokens: int, current_cost: float, baseline_cost: float) -> float:
    if value is not None:
        return round(float_or_zero(value), 4)
    if baseline_tokens > 0:
        return round((current_tokens - baseline_tokens) / baseline_tokens, 4)
    if baseline_cost > 0:
        return round((current_cost - baseline_cost) / baseline_cost, 4)
    return 0.0


def _status(value: Any, delta_ratio: float, baseline_missing: bool) -> str:
    explicit = _bucket(value, "")
    if explicit in STATUS_RANK:
        return explicit
    if baseline_missing:
        return "medium"
    magnitude = abs(delta_ratio)
    if magnitude >= 2:
        return "critical"
    if magnitude >= 1:
        return "high"
    if magnitude >= 0.25:
        return "medium"
    return "low"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"status": "critical" if counts["critical"] else ("high" if counts["high"] else ("medium" if counts["medium"] else "low")), "model_count": len(rows), "anomaly_count": sum(1 for row in rows if row["status"] != "low"), "baseline_missing_count": sum(1 for row in rows if row["baseline_missing"])}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "model_count": counts[status]} for status in ("critical", "high", "medium", "low")]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
