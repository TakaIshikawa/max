"""JSON API renderer for LLM provider failover status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.llm_provider_failover_status.v1"
KIND = "max.api.llm_provider_failover_status"
STATUS_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def llm_provider_failover_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    providers = _providers(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(providers),
        "providers": providers,
        "status_totals": _status_totals(providers),
        "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, provider_count=len(providers)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _providers(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("providers") if isinstance(payload.get("providers"), list) else payload.get("failovers")
    rows = [_provider(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["trigger_count"], row["provider"]))


def _provider(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    triggers = max(0, int_or_zero(item.get("trigger_count", item.get("triggers"))))
    state = _bucket(item.get("recovery_state") or item.get("state"), "healthy")
    status = _status(item.get("status") or item.get("severity"), triggers, state)
    return {
        "provider": _text(item.get("provider")) or f"provider-{index}",
        "primary_model": _text(item.get("primary_model")) or "unknown-primary",
        "fallback_model": _text(item.get("fallback_model")) or "unknown-fallback",
        "trigger_count": triggers,
        "last_triggered_at": _timestamp(item.get("last_triggered_at") or item.get("last_failover_at")),
        "recovery_state": state,
        "status": status,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    overall = "critical" if counts["critical"] else ("high" if counts["high"] else ("medium" if counts["medium"] else "low"))
    return {"status": overall, "health": "healthy" if overall == "low" else "degraded", "provider_count": len(rows), "critical_count": counts["critical"], "high_count": counts["high"], "medium_count": counts["medium"], "low_count": counts["low"], "trigger_count": sum(row["trigger_count"] for row in rows)}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "provider_count": counts[status]} for status in ("critical", "high", "medium", "low")]


def _status(value: Any, triggers: int, state: str) -> str:
    explicit = _bucket(value, "")
    if explicit in STATUS_RANK:
        return explicit
    if state in {"failed", "unavailable", "stuck"} or triggers >= 10:
        return "critical"
    if state in {"degraded", "fallback_active"} or triggers >= 5:
        return "high"
    if state in {"recovering", "cooling_down"} or triggers > 0:
        return "medium"
    return "low"


def _timestamp(value: Any) -> str | None:
    return datetime_to_string(parse_datetime(value))


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace("-", "_").replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
