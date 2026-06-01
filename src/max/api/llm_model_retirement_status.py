"""JSON API renderer for LLM model retirement status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata, strings

SCHEMA_VERSION = "max.api.llm_model_retirement_status.v1"
KIND = "max.api.llm_model_retirement_status"
RANK = {"retired": 0, "retiring_soon": 1, "deprecated": 2, "supported": 3, "unknown": 4}


def llm_model_retirement_status_to_json(payload: Mapping[str, Any], *, as_of: datetime | str | None = None) -> str:
    checked_at = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    window = max(0, int_or_zero(payload.get("retiring_soon_days") or payload.get("warning_days") or 30))
    rows = [_model(row, i, checked_at, window) for i, row in enumerate(list_of_maps(payload.get("models") or payload.get("configured_models") or payload.get("configurations") or payload.get("items") or payload.get("rows")), start=1)]
    rows = sorted(rows, key=lambda row: (RANK[row["status"]], row["days_until_retirement"] if row["days_until_retirement"] is not None else 10**9, row["model"].casefold()))
    counts = {name + "_count": sum(1 for row in rows if row["status"] == name) for name in RANK}
    status = "critical" if counts["retired_count"] else ("warning" if counts["retiring_soon_count"] or counts["deprecated_count"] else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": _stamp(checked_at), "status": status, "summary": {"model_count": len(rows), **counts}, "impacted_models": [row for row in rows if row["status"] != "supported"], "models": rows, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _model(item: Mapping[str, Any], index: int, as_of: datetime, window: int) -> dict[str, Any]:
    retirement = parse_datetime(item.get("retirement_date") or item.get("retires_at") or item.get("retirement_at"))
    days = (retirement.date() - as_of.date()).days if retirement else None
    deprecated = bool(item.get("deprecated")) or _text(item.get("lifecycle_status")).casefold() == "deprecated"
    retired = days is not None and days < 0
    soon = days is not None and 0 <= days <= window
    status = "retired" if retired else ("retiring_soon" if soon else ("deprecated" if deprecated else ("supported" if retirement or not deprecated else "unknown")))
    fallback = bool(item.get("fallback_ready") or item.get("fallback_model"))
    return {"model": _text(item.get("model") or item.get("model_id") or item.get("name")) or f"model-{index}", "provider": _text(item.get("provider")) or None, "retirement_date": _stamp(retirement) if retirement else None, "days_until_retirement": days, "deprecated": deprecated, "fallback_ready": fallback, "impacted_stages": strings(item.get("impacted_stages") or item.get("stages")), "status": status, "next_actions": _actions(status, fallback)}


def _actions(status: str, fallback: bool) -> list[str]:
    if status == "retired":
        return ["disable retired model usage", "route traffic to fallback model" if fallback else "configure fallback model"]
    if status in {"retiring_soon", "deprecated"}:
        return ["schedule model migration", "validate fallback readiness" if not fallback else "test fallback switchover"]
    return ["continue monitoring model lifecycle"]


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
