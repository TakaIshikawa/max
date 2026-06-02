"""JSON API renderer for spec publication dead letter status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import bool_or_default, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.spec_publication_dead_letter_status.v1"
KIND = "max.api.spec_publication_dead_letter_status"


def spec_publication_dead_letter_status_to_json(payload: Mapping[str, Any]) -> str:
    specs = [_spec(row) for row in _items(payload)]
    specs.sort(key=lambda row: (-row["failed_attempts"], row["destination"], row["spec_id"]))
    retryable = sum(1 for row in specs if row["retryable"])
    terminal = len(specs) - retryable
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": "critical" if terminal else "warning" if retryable else "ok", "terminal_count": terminal, "retryable_count": retryable, "destinations": _counts(specs, "destination"), "error_families": _counts(specs, "error_family"), "worst_specs": specs[:10], "metadata": source_metadata(payload, spec_count=len(specs))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("specs")) or list_of_maps(payload.get("dead_letters")) or list_of_maps(payload.get("items"))


def _spec(row: Mapping[str, Any]) -> dict[str, Any]:
    error = _text(row.get("last_error") or row.get("error")) or "unknown"
    return {"spec_id": _text(row.get("spec_id") or row.get("id")) or "unknown_spec", "destination": _bucket(row.get("destination"), "unknown_destination"), "failed_attempts": max(0, int_or_zero(row.get("failed_attempts") or row.get("attempt_count"))), "last_error": error, "error_family": _family(error), "last_failed_at": _text(row.get("last_failed_at")) or None, "retryable": bool_or_default(row.get("retryable"), default=False)}


def _counts(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(row[key] for row in rows)
    return [{key: name, "count": count} for name, count in sorted(counts.items())]


def _family(error: str) -> str:
    lowered = error.lower()
    if not lowered or lowered == "unknown":
        return "unknown"
    return lowered.split(":", 1)[0].split()[0]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
