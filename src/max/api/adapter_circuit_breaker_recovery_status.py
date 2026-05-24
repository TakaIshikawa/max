"""JSON API renderer for adapter circuit breaker recovery status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.adapter_circuit_breaker_recovery_status.v1"
KIND = "max.api.adapter_circuit_breaker_recovery_status"
STATUS_RANK = {"stuck": 0, "open": 1, "cooling_down": 2, "ready": 3}


def adapter_circuit_breaker_recovery_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    adapters = _adapters(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(adapters),
        "adapters": adapters,
        "status_totals": _status_totals(adapters),
        "blocked_adapters": [row["adapter"] for row in adapters if row["status"] in {"open", "stuck"}],
        "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, adapter_count=len(adapters)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _adapters(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("adapters") if isinstance(payload.get("adapters"), list) else payload.get("circuit_breakers")
    rows = [_adapter(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["adapter"], row["source"]))


def _adapter(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    state = _state(item.get("state", item.get("breaker_state")))
    failures = max(0, int_or_zero(item.get("failure_streak", item.get("failed_probe_count"))))
    cooldown = max(0, int_or_zero(item.get("cooldown_remaining_seconds", item.get("cooldown_remaining"))))
    retry_after = max(0, int_or_zero(item.get("retry_after_seconds", item.get("retry_after"))))
    if state == "closed":
        status = "ready"
    elif state == "half_open":
        status = "stuck" if failures >= 3 else "ready"
    elif cooldown > 0 or retry_after > 0:
        status = "cooling_down"
    else:
        status = "stuck" if failures >= 5 else "open"
    return {
        "adapter": _text(item.get("adapter") or item.get("adapter_name")) or f"adapter-{index}",
        "source": _text(item.get("source") or item.get("source_id")) or "unknown-source",
        "state": state,
        "failure_streak": failures,
        "cooldown_remaining_seconds": cooldown,
        "retry_after_seconds": retry_after,
        "last_recovery_attempt_at": item.get("last_recovery_attempt_at") or item.get("last_attempt_at"),
        "status": status,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"adapter_count": len(rows), "ready_count": counts["ready"], "cooling_down_count": counts["cooling_down"], "open_count": counts["open"], "stuck_count": counts["stuck"]}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "adapter_count": counts[status]} for status in ("stuck", "open", "cooling_down", "ready")]


def _state(value: Any) -> str:
    state = _text(value).lower().replace("-", "_").replace(" ", "_")
    return state if state in {"closed", "half_open", "open"} else "closed"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

