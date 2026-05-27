"""JSON API renderer for run checkpoint retention status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import bool_or_default, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.run_checkpoint_retention_status.v1"
KIND = "max.api.run_checkpoint_retention_status"


def run_checkpoint_retention_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "cleanup_candidates": [row for row in rows if row["expired"] and not row["protected"]], "metadata": source_metadata(payload, checkpoint_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("checkpoints") if isinstance(payload.get("checkpoints"), list) else payload.get("items")
    rows = [_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (not (row["expired"] and not row["protected"]), row["run_id"], row["checkpoint_id"]))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    age = max(0, int_or_zero(item.get("age_days")))
    retention = max(0, int_or_zero(item.get("retention_days")))
    protected = bool_or_default(item.get("protected"), default=False)
    expired = bool(retention and age > retention and not protected)
    return {"run_id": _text(item.get("run_id")) or f"run-{index}", "checkpoint_id": _text(item.get("checkpoint_id")) or f"checkpoint-{index}", "stage": _bucket(item.get("stage"), "unknown"), "age_days": age, "retention_days": retention, "expired": expired, "protected": protected, "cleanup_action": _text(item.get("cleanup_action")) or ("delete checkpoint" if expired else "retain")}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cleanup = [row for row in rows if row["expired"] and not row["protected"]]
    return {"status": "cleanup_due" if cleanup else "retained", "checkpoint_count": len(rows), "expired_count": sum(1 for row in rows if row["expired"]), "protected_count": sum(1 for row in rows if row["protected"]), "cleanup_candidate_count": len(cleanup)}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
