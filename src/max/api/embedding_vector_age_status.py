"""JSON API renderer for embedding vector age status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.embedding_vector_age_status.v1"
KIND = "max.api.embedding_vector_age_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def embedding_vector_age_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_stale_rate"), 0.1)
    critical = _float(payload.get("critical_stale_rate"), 0.25)
    rows = sorted([_row(item, index, warning, critical) for index, item in enumerate(_items(payload), start=1)], key=lambda row: (STATUS_RANK[row["status"]], -row["stale_rate"], row["index"]))
    summary = _summary(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "indexes": rows, "metadata": source_metadata(payload, index_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("indexes") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    total = max(0, int_or_zero(item.get("vector_count")))
    stale = max(0, int_or_zero(item.get("stale_vector_count")))
    rate = round(stale / total, 4) if total else 0.0
    model = _text(item.get("embedding_model"))
    expected = _text(item.get("expected_model"))
    mismatch = bool(model and expected and model != expected)
    status = "critical" if rate >= critical or mismatch else "warning" if rate >= warning else "ok"
    return {"index": _text(item.get("index")) or f"index-{index}", "vector_count": total, "stale_vector_count": stale, "stale_rate": rate, "oldest_vector_age_days": max(0.0, float_or_zero(item.get("oldest_vector_age_days"))), "embedding_model": model, "expected_model": expected, "model_mismatch": mismatch, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "index_count": len(rows), "stale_index_count": critical + warning, "model_mismatch_count": sum(1 for row in rows if row["model_mismatch"]), "critical_count": critical, "warning_count": warning, "max_stale_rate": max((row["stale_rate"] for row in rows), default=0.0)}


def _float(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
