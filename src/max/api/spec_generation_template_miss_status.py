"""JSON API renderer for spec generation template miss status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.spec_generation_template_miss_status.v1"
KIND = "max.api.spec_generation_template_miss_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def spec_generation_template_miss_status_to_json(payload: Mapping[str, Any], *, retry_warning_threshold: int = 2) -> str:
    rows = [_row(item, index, retry_warning_threshold) for index, item in enumerate(_items(payload), start=1)]
    rows = sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["missing_block_count"], row["spec_id"]))
    blocks = Counter(block for row in rows for block in row["missing_blocks"])
    common = blocks.most_common(1)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"spec_count": len(rows), "affected_specs": sum(1 for row in rows if row["status"] != "ok"), "critical_specs": sum(1 for row in rows if row["status"] == "critical"), "missing_block_count": sum(row["missing_block_count"] for row in rows), "most_common_missing_block": common[0][0] if common else None}, "spec_rows": rows, "metadata": source_metadata(payload, spec_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("specs") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, retry_warning: int) -> dict[str, Any]:
    blocks = _strings(item.get("missing_blocks"))
    variables = _strings(item.get("missing_variables"))
    retries = max(0, int_or_zero(item.get("retry_count")))
    failed = _text(item.get("generation_status")).casefold() in {"failed", "error", "blocked"}
    status = "critical" if failed and blocks else "warning" if blocks or variables or retries >= retry_warning else "ok"
    return {"spec_id": _text(item.get("spec_id") or item.get("unit_id")) or f"spec-{index}", "template_name": _text(item.get("template_name")) or None, "missing_blocks": blocks, "missing_variables": variables, "missing_block_count": len(blocks), "generation_status": _text(item.get("generation_status")) or "ok", "retry_count": retries, "status": status}


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({_text(item) for item in value if _text(item)})
    text = _text(value)
    return [text] if text else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
