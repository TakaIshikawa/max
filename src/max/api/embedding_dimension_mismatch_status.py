"""JSON API renderer for embedding dimension mismatch status."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.embedding_dimension_mismatch_status.v1"
KIND = "max.api.embedding_dimension_mismatch_status"
STATUS_RANK = {"incompatible": 0, "drifted": 1, "compatible": 2}


def embedding_dimension_mismatch_status_to_json(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]], *, incompatible_rate: float = 50.0) -> str:
    expected = mapping(payload.get("expected_dimensions")) if isinstance(payload, Mapping) else {}
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _items(payload):
        key = (_text(item.get("index") or item.get("index_name")) or "unknown", _text(item.get("provider")) or "unknown")
        group = groups.setdefault(key, {"index_name": key[0], "provider": key[1], "record_count": 0, "mismatch_count": 0, "affected_record_ids": []})
        group["record_count"] += 1
        expected_dimensions = int_or_zero(item.get("expected_dimensions", expected.get(key[0], expected.get(key[1]))))
        actual_dimensions = int_or_zero(item.get("actual_dimensions", item.get("dimensions")))
        group["expected_dimensions"] = expected_dimensions
        if expected_dimensions and actual_dimensions != expected_dimensions:
            group["mismatch_count"] += 1
            record_id = _text(item.get("record_id") or item.get("id"))
            if record_id:
                group["affected_record_ids"].append(record_id)
    rows = [_finish_group(group, incompatible_rate) for group in groups.values()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["index_name"], row["provider"]))
    metadata = source_metadata(payload if isinstance(payload, Mapping) else {}, group_count=len(rows))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "indexes": rows, "metadata": metadata}, indent=2, sort_keys=True)


def _finish_group(group: dict[str, Any], incompatible_rate: float) -> dict[str, Any]:
    rate = round((group["mismatch_count"] / group["record_count"]) * 100, 2) if group["record_count"] else 0.0
    status = "incompatible" if rate >= incompatible_rate and group["mismatch_count"] else "drifted" if group["mismatch_count"] else "compatible"
    return {**group, "affected_record_ids": sorted(set(group["affected_record_ids"])), "mismatch_rate": rate, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "incompatible" if any(row["status"] == "incompatible" for row in rows) else "drifted" if any(row["status"] == "drifted" for row in rows) else "compatible", "group_count": len(rows), "record_count": sum(row["record_count"] for row in rows), "mismatch_count": sum(row["mismatch_count"] for row in rows)}


def _items(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return list_of_maps(payload.get("records") or payload.get("embeddings") or payload.get("rows") or payload.get("items"))
    return [item for item in payload if isinstance(item, Mapping)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
