"""JSON API renderer for prompt failure recovery status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.prompt_failure_recovery_status.v1"
KIND = "max.api.prompt_failure_recovery_status"


def prompt_failure_recovery_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item) for item in _items(payload)]
    failure_count = _count(payload, "failure_count", sum(row["failure_count"] for row in rows))
    retry_count = _count(payload, "retry_count", sum(row["retry_count"] for row in rows))
    recovered = _count(payload, "recovered_count", sum(row["recovered_count"] for row in rows))
    unrecovered = _count(payload, "unrecovered_count", max(0, failure_count - recovered))
    rate = round(recovered / failure_count, 4) if failure_count else 1.0
    status = "ok" if failure_count == 0 or unrecovered == 0 else "warning"
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "failure_count": failure_count,
            "retry_count": retry_count,
            "recovered_count": recovered,
            "unrecovered_count": unrecovered,
            "recovery_rate": rate,
            "prompts": rows,
            "metadata": source_metadata(payload, prompt_count=len(rows)),
        },
        indent=2,
        sort_keys=True,
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("prompts") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    failures = max(0, int_or_zero(item.get("failure_count")))
    recovered = max(0, int_or_zero(item.get("recovered_count")))
    return {
        "prompt": _text(item.get("prompt") or item.get("prompt_name") or item.get("id")) or "unknown",
        "failure_count": failures,
        "retry_count": max(0, int_or_zero(item.get("retry_count"))),
        "recovered_count": recovered,
        "unrecovered_count": max(0, int_or_zero(item.get("unrecovered_count") if item.get("unrecovered_count") is not None else failures - recovered)),
    }


def _count(payload: Mapping[str, Any], key: str, default: int) -> int:
    return max(0, int_or_zero(payload.get(key))) if payload.get(key) is not None else max(0, default)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
