"""JSON API renderer for source adapter error budget status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_error_budget_status.v1"
KIND = "max.api.source_adapter_error_budget_status"


def source_adapter_error_budget_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "over_budget_sources": [row for row in rows if row["status"] == "over_budget"], "metadata": source_metadata(payload, source_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("sources") if isinstance(payload.get("sources"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (row["status"] != "over_budget", -row["burn_ratio"], row["source"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    allowed = max(0, int_or_zero(item.get("allowed_errors")))
    consumed = max(0, int_or_zero(item.get("consumed_errors")))
    remaining = max(allowed - consumed, 0)
    burn = round(consumed / allowed, 4) if allowed else (1.0 if consumed else 0.0)
    status = "over_budget" if consumed > allowed or (allowed == 0 and consumed > 0) else "warning" if burn >= 0.8 else "healthy"
    return {"source": _bucket(item.get("source") or item.get("source_id"), "unknown_source"), "adapter": _bucket(item.get("adapter"), "unknown_adapter"), "allowed_errors": allowed, "consumed_errors": consumed, "remaining_budget": remaining, "burn_ratio": burn, "status": status, "recommended_action": "pause ingestion and investigate errors" if status == "over_budget" else "reduce adapter error rate" if status == "warning" else "none"}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    over = sum(1 for row in rows if row["status"] == "over_budget")
    warn = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "over_budget" if over else "warning" if warn else "healthy", "source_count": len(rows), "over_budget_count": over, "warning_count": warn}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
