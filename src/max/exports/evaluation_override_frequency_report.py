"""Evaluation override frequency export report."""

from __future__ import annotations

import json
from typing import Any, Iterable


def build_evaluation_override_frequency_report(records: Iterable[Any], *, override_threshold: float = 0.25) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for raw in records:
        recommendation = _norm(_get(raw, "recommendation") or _get(raw, "automated_recommendation")) or "unknown"
        outcome = _norm(_get(raw, "reviewer_outcome") or _get(raw, "outcome")) or "unknown"
        profile = _text(_get(raw, "profile")) or "unknown-profile"
        period = _period(_get(raw, "timestamp") or _get(raw, "created_at") or _get(raw, "reviewed_at"))
        key = (profile, period, recommendation, outcome)
        row = groups.setdefault(key, {"profile": profile, "period": period, "recommendation": recommendation, "reviewer_outcome": outcome, "evaluation_count": 0, "override_count": 0, "override_rate": 0.0, "overridden_dimensions": {}, "flagged": False})
        count = _int(_get(raw, "count") or 1)
        row["evaluation_count"] += count
        overridden = recommendation != outcome and outcome != "unknown"
        if overridden:
            row["override_count"] += count
            dimension = _text(_get(raw, "dimension")) or "unknown-dimension"
            row["overridden_dimensions"][dimension] = row["overridden_dimensions"].get(dimension, 0) + count
    rows = []
    for row in groups.values():
        row["override_rate"] = round(row["override_count"] / row["evaluation_count"], 4) if row["evaluation_count"] else 0.0
        row["top_overridden_dimensions"] = [name for name, _ in sorted(row.pop("overridden_dimensions").items(), key=lambda item: (-item[1], item[0].lower()))[:5]]
        row["flagged"] = row["override_rate"] >= override_threshold
        rows.append(row)
    rows.sort(key=lambda row: (row["profile"].lower(), row["period"], row["recommendation"], row["reviewer_outcome"]))
    return {"schema_version": "max.evaluation_override_frequency_report.v1", "kind": "max.evaluation_override_frequency_report", "summary": {"row_count": len(rows), "flagged_recommendation_count": sum(1 for row in rows if row["flagged"])}, "rows": rows, "flagged_recommendations": [row for row in rows if row["flagged"]]}


def render_evaluation_override_frequency_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_evaluation_override_frequency_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Evaluation Override Frequency Report", "", "| Profile | Period | Recommendation | Outcome | Evaluations | Overrides | Rate | Flagged |", "| --- | --- | --- | --- | ---: | ---: | ---: | --- |"]
    for row in report.get("rows", []):
        lines.append(f"| {row['profile']} | {row['period']} | {row['recommendation']} | {row['reviewer_outcome']} | {row['evaluation_count']} | {row['override_count']} | {row['override_rate']} | {row['flagged']} |")
    return "\n".join(lines).rstrip() + "\n"


def _get(raw: Any, key: str) -> Any:
    return raw.get(key) if isinstance(raw, dict) else getattr(raw, key, None)


def _period(value: Any) -> str:
    text = _text(value)
    return text[:7] if len(text) >= 7 else "unbucketed"


def _norm(value: Any) -> str:
    return _text(value).lower().replace(" ", "_").replace("-", "_")


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
