"""JSON API renderer for LLM prompt drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.llm_prompt_drift_status.v1"
KIND = "max.api.llm_prompt_drift_status"


def llm_prompt_drift_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_mismatch_ratio"), 0.1)
    critical = _float(payload.get("critical_mismatch_ratio"), 0.25)
    rows = [_row(item, index) for index, item in enumerate(list_of_maps(payload.get("prompts") or payload.get("rows")), start=1)]
    stale = [row for row in rows if row["mismatched"]]
    stale.sort(key=lambda row: (row["family"], row["prompt_id"]))
    ratio = round(len(stale) / len(rows), 4) if rows else 0.0
    status = "critical" if ratio >= critical and stale else ("warning" if ratio >= warning and stale else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "total_prompts": len(rows), "mismatched_prompts": len(stale), "mismatch_ratio": ratio}, "prompts": sorted(rows, key=lambda row: (not row["mismatched"], row["family"], row["prompt_id"])), "stale_versions": stale, "families": _families(rows), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    active = str(item.get("active_version") or item.get("version") or "")
    expected = str(item.get("expected_version") or item.get("profile_version") or item.get("pipeline_version") or "")
    return {"prompt_id": str(item.get("prompt_id") or item.get("id") or f"prompt-{index}"), "family": str(item.get("family") or item.get("prompt_family") or "unknown_family"), "active_version": active, "expected_version": expected, "mismatched": bool(active and expected and active != expected)}


def _families(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    families = sorted({row["family"] for row in rows})
    return [{"family": family, "total_prompts": sum(1 for row in rows if row["family"] == family), "mismatched_prompts": sum(1 for row in rows if row["family"] == family and row["mismatched"])} for family in families]


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default
