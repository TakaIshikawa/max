"""JSON API renderer for LLM retry storm status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.llm_retry_storm_status.v1"
KIND = "max.api.llm_retry_storm_status"


def llm_retry_storm_status_to_json(payload: Mapping[str, Any]) -> str:
    rate_threshold = float(payload.get("retry_rate_threshold") or 0.2)
    count_threshold = int_or_zero(payload.get("retry_count_threshold") or 10)
    rows = [_row(item, rate_threshold, count_threshold) for item in list_of_maps(payload.get("attempts") or payload.get("items"))]
    rows.sort(key=lambda row: (not row["storming"], -row["retry_pressure"], row["provider"], row["model"], row["window"]))
    storms = [row for row in rows if row["storming"]]
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "storming" if storms else "ok", "provider_count": len({row["provider"] for row in rows}), "storm_count": len(storms), "retry_attempt_count": sum(row["retry_count"] for row in rows)}, "rows": rows, "storming_groups": storms, "metadata": source_metadata(payload, retry_rate_threshold=rate_threshold, retry_count_threshold=count_threshold)}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], rate_threshold: float, count_threshold: int) -> dict[str, Any]:
    retries = max(0, int_or_zero(item.get("retry_count") if item.get("retry_count") is not None else item.get("retries") if item.get("retries") is not None else item.get("failures")))
    total = max(0, int_or_zero(item.get("total_requests") if item.get("total_requests") is not None else item.get("attempts")))
    rate = round(retries / total, 4) if total else (1.0 if retries else 0.0)
    storming = rate >= rate_threshold or retries >= count_threshold
    return {"provider": _bucket(item.get("provider"), "unknown_provider"), "model": _bucket(item.get("model"), "unknown_model"), "window": str(item.get("window") or "current"), "total_requests": total, "retry_count": retries, "retry_rate": rate, "retry_pressure": max(rate, retries / count_threshold if count_threshold else 0), "storming": storming, "severity": "critical" if storming and retries >= count_threshold * 2 else "warning" if storming else "ok", "recommended_action": "failover_or_throttle" if storming else "none"}


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
