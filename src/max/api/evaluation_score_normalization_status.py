"""JSON API renderer for evaluation score normalization status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.evaluation_score_normalization_status.v1"
KIND = "max.api.evaluation_score_normalization_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def evaluation_score_normalization_status_to_json(payload: Mapping[str, Any], *, required_dimensions: tuple[str, ...] = ("impact", "confidence", "effort"), max_score: float = 1.0, total_tolerance: float = 0.01) -> str:
    rows = [_row(item, index, required_dimensions, max_score, total_tolerance) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -len(row["issues"]), row["idea_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"record_count": len(rows), "issue_count": sum(len(row["issues"]) for row in rows), "critical_count": sum(1 for row in rows if row["status"] == "critical"), "status": "critical" if any(row["status"] == "critical" for row in rows) else "warning" if any(row["status"] == "warning" for row in rows) else "ok"}, "score_rows": rows, "metadata": source_metadata(payload, record_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("evaluations") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, dimensions: tuple[str, ...], max_score: float, tolerance: float) -> dict[str, Any]:
    scores = mapping(item.get("scores") or item.get("dimensions"))
    normalized = {name: round(float_or_zero(scores.get(name)), 4) for name in sorted(set(dimensions) | {str(key) for key in scores})}
    issues = []
    for name in dimensions:
        if name not in scores:
            issues.append(f"missing:{name}")
    for name, value in normalized.items():
        if value < 0:
            issues.append(f"below_min:{name}")
        if value > max_score:
            issues.append(f"above_max:{name}")
    total = round(sum(normalized.values()), 4)
    expected_total = float_or_zero(item.get("normalized_total") or item.get("total_score"))
    if expected_total and abs(total - expected_total) > tolerance:
        issues.append("total_mismatch")
    status = "critical" if any(issue.startswith(("missing:", "below_min:", "above_max:")) for issue in issues) else "warning" if issues else "ok"
    return {"idea_id": _text(item.get("idea_id") or item.get("id")) or f"idea-{index}", "scores": normalized, "score_total": total, "reported_total": round(expected_total, 4), "issues": sorted(issues), "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
