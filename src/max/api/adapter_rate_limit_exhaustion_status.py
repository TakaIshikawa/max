"""JSON API renderer for adapter rate limit exhaustion status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.adapter_rate_limit_exhaustion_status.v1"
KIND = "max.api.adapter_rate_limit_exhaustion_status"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def adapter_rate_limit_exhaustion_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "adapters": rows, "metadata": source_metadata(payload, adapter_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("adapters") if isinstance(payload.get("adapters"), list) else payload.get("quotas")
    rows = [_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (SEVERITY_RANK[row["severity"]], row["remaining_quota"], row["adapter"]))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    limit = int_or_zero(item.get("quota_limit", item.get("limit")))
    remaining = int_or_zero(item.get("remaining_quota", item.get("remaining")))
    ratio = remaining / limit if limit else (1.0 if remaining > 0 else 0.0)
    severity = "critical" if remaining <= 0 else ("warn" if ratio <= 0.1 else "ok")
    return {"adapter": _text(item.get("adapter") or item.get("name")) or f"adapter-{index}", "remaining_quota": remaining, "quota_limit": limit, "remaining_ratio": round(ratio, 4), "reset_at": item.get("reset_at"), "reset_after_seconds": int_or_zero(item.get("reset_after_seconds")), "exhausted": remaining <= 0, "severity": severity}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"adapter_count": len(rows), "exhausted_count": sum(1 for row in rows if row["exhausted"]), "warning_count": sum(1 for row in rows if row["severity"] == "warn"), "total_remaining_quota": sum(row["remaining_quota"] for row in rows), "severity": min((row["severity"] for row in rows), key=lambda value: SEVERITY_RANK[value], default="ok")}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
