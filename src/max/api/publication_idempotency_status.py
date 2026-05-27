"""JSON API renderer for publication idempotency status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata, strings

SCHEMA_VERSION = "max.api.publication_idempotency_status.v1"
KIND = "max.api.publication_idempotency_status"


def publication_idempotency_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "collisions": [row for row in rows if row["collision"]], "metadata": source_metadata(payload, attempt_group_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("attempts") if isinstance(payload.get("attempts"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["collision"], row["destination"], row["idempotency_key"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    attempts = max(0, int_or_zero(item.get("attempt_count")))
    duplicates = max(0, int_or_zero(item.get("duplicate_count")))
    external_ids = strings(item.get("external_ids") or item.get("external_id"))
    collision = bool(duplicates or (attempts > 1 and len(external_ids) > 1))
    return {"destination": _bucket(item.get("destination"), "unknown_destination"), "idempotency_key": _text(item.get("idempotency_key")) or "unknown-key", "attempt_count": attempts, "duplicate_count": duplicates, "last_attempt_at": _text(item.get("last_attempt_at")) or None, "collision": collision, "action": _text(item.get("action")) or ("investigate duplicate publication" if collision else "none")}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    collisions = [row for row in rows if row["collision"]]
    return {"status": "collision_detected" if collisions else "deduplicated", "publication_count": len(rows), "total_attempts": sum(row["attempt_count"] for row in rows), "duplicate_count": sum(row["duplicate_count"] for row in rows), "collision_count": len(collisions), "affected_destinations": sorted({row["destination"] for row in collisions})}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
