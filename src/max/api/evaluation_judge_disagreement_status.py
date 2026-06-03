"""JSON API renderer for evaluation judge disagreement status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.evaluation_judge_disagreement_status.v1"
KIND = "max.api.evaluation_judge_disagreement_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def evaluation_judge_disagreement_status_to_json(payload: Mapping[str, Any]) -> str:
    warning_rate = _float(payload.get("warning_disagreement_rate"), 0.2)
    critical_rate = _float(payload.get("critical_disagreement_rate"), 0.35)
    warning_stddev = _float(payload.get("warning_score_stddev"), 1.0)
    critical_stddev = _float(payload.get("critical_score_stddev"), 2.0)
    rows = sorted([_row(item, index, warning_rate, critical_rate, warning_stddev, critical_stddev) for index, item in enumerate(_items(payload), start=1)], key=lambda row: (STATUS_RANK[row["status"]], -row["disagreement_rate"], row["profile"], row["dimension"]))
    summary = _summary(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "evaluations": rows, "metadata": source_metadata(payload, dimension_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("evaluations") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int, wr: float, cr: float, ws: float, cs: float) -> dict[str, Any]:
    judges = max(0, int_or_zero(item.get("judge_count")))
    disagreements = max(0, int_or_zero(item.get("disagreement_count")))
    rate = round(disagreements / judges, 4) if judges else 0.0
    stddev = max(0.0, float_or_zero(item.get("score_stddev")))
    status = "critical" if rate >= cr or stddev >= cs else "warning" if rate >= wr or stddev >= ws else "ok"
    return {"profile": _text(item.get("profile")) or "unknown", "dimension": _text(item.get("dimension")) or f"dimension-{index}", "judge_count": judges, "disagreement_count": disagreements, "disagreement_rate": rate, "score_stddev": stddev, "recommendation_split": dict(sorted(mapping(item.get("recommendation_split")).items())), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "dimension_count": len(rows), "unstable_dimension_count": critical + warning, "critical_count": critical, "warning_count": warning, "max_disagreement_rate": max((row["disagreement_rate"] for row in rows), default=0.0)}


def _float(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
