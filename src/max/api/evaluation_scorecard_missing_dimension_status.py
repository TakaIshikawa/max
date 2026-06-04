"""JSON API renderer for evaluation scorecard missing dimension status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, mapping, source_metadata, strings

SCHEMA_VERSION = "max.api.evaluation_scorecard_missing_dimension_status.v1"
KIND = "max.api.evaluation_scorecard_missing_dimension_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def evaluation_scorecard_missing_dimension_status_to_json(
    payload: Any,
    *,
    warning_coverage_ratio: float = 0.9,
    critical_coverage_ratio: float = 0.5,
) -> str:
    payload_map = mapping(payload)
    evaluations = _evaluations(payload, warning_coverage_ratio, critical_coverage_ratio)
    status = _overall_status(evaluations)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "summary": {
                "scorecard_count": len(evaluations),
                "incomplete_scorecard_count": sum(1 for row in evaluations if row["missing_dimensions"]),
                "min_coverage_ratio": min((row["coverage_ratio"] for row in evaluations), default=0.0),
                "status": status,
            },
            "evaluations": evaluations,
            "metadata": source_metadata(payload_map, scorecard_count=len(evaluations)),
        },
        indent=2,
        sort_keys=True,
    )


def _evaluations(payload: Any, warning_coverage_ratio: float, critical_coverage_ratio: float) -> list[dict[str, Any]]:
    payload_map = mapping(payload)
    source = payload_map.get("evaluations") or payload_map.get("items") or (payload if isinstance(payload, list) else [])
    rows = [_evaluation(row, index, warning_coverage_ratio, critical_coverage_ratio) for index, row in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["coverage_ratio"], row["evaluation_id"]))


def _evaluation(item: Mapping[str, Any], index: int, warning_coverage_ratio: float, critical_coverage_ratio: float) -> dict[str, Any]:
    expected = strings(item.get("expected_dimensions"))
    scored = strings(item.get("scored_dimensions"))
    missing = sorted(set(expected) - set(scored))
    coverage_ratio = round((len(expected) - len(missing)) / len(expected), 4) if expected else 0.0
    if coverage_ratio < critical_coverage_ratio:
        status = "critical"
    elif coverage_ratio < warning_coverage_ratio:
        status = "warning"
    else:
        status = "ok"
    return {
        "evaluation_id": _text(item.get("evaluation_id") or item.get("id")) or f"evaluation-{index}",
        "unit_id": _text(item.get("unit_id")) or None,
        "profile": _text(item.get("profile")) or "default",
        "expected_dimensions": expected,
        "scored_dimensions": scored,
        "missing_dimensions": missing,
        "coverage_ratio": coverage_ratio,
        "recommendation": _text(item.get("recommendation")) or None,
        "status": status,
    }


def _overall_status(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
