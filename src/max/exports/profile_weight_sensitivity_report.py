"""Profile weight sensitivity export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.profile_weight_sensitivity_report.v1"
KIND = "max.profile_weight_sensitivity_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class ProfileWeightSensitivityInput(TypedDict, total=False):
    profile: str
    dimension: str
    baseline_weight: int | float | str
    proposed_weight: int | float | str
    affected_idea_count: int | float | str
    average_score_delta: int | float | str
    recommendation_change_count: int | float | str
    rationale: str


def build_profile_weight_sensitivity_report(
    records: Iterable[ProfileWeightSensitivityInput | dict[str, Any]],
    *,
    title: str = "Profile Weight Sensitivity Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = _normalize_records(records)
    largest = sorted(rows, key=lambda row: (-abs(row["weight_delta"]), row["profile"].lower(), row["dimension"].lower()))
    sensitive = [row for row in rows if row["recommendation_change_count"] > 0]
    risk = _profile_risks(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Profile Weight Sensitivity Report",
        "summary": {
            "dimension_count": len(rows),
            "largest_weight_delta": max((abs(row["weight_delta"]) for row in rows), default=0.0),
            "recommendation_change_count": sum(row["recommendation_change_count"] for row in rows),
            "high_risk_profile_count": sum(1 for row in risk if row["risk_level"] == "high"),
        },
        "dimension_sensitivity": rows,
        "largest_weight_shifts": largest,
        "recommendation_sensitive_dimensions": sorted(sensitive, key=lambda row: (-row["recommendation_change_count"], -abs(row["average_score_delta"]), row["profile"].lower(), row["dimension"].lower())),
        "profile_risk_levels": risk,
        "review_actions": [
            {
                "profile": row["profile"],
                "dimension": row["dimension"],
                "risk_level": row["risk_level"],
                "action": f"Review {row['dimension']} weight change for {row['profile']}.",
            }
            for row in rows
            if row["risk_level"] in {"high", "medium"}
        ],
    }


def render_profile_weight_sensitivity_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join(
        [
            f"# {report.get('title') or 'Profile Weight Sensitivity Report'}",
            "",
            "## Summary",
            "",
            f"- Dimensions: {summary.get('dimension_count', 0)}",
            f"- Recommendation changes: {summary.get('recommendation_change_count', 0)}",
            f"- High risk profiles: {summary.get('high_risk_profile_count', 0)}",
        ]
    ).rstrip() + "\n"


def render_profile_weight_sensitivity_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[ProfileWeightSensitivityInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for raw in records:
        baseline = _float(raw.get("baseline_weight"))
        proposed = _float(raw.get("proposed_weight"))
        changes = _int(raw.get("recommendation_change_count"))
        delta = round(proposed - baseline, 4)
        score_delta = round(_float(raw.get("average_score_delta"), signed=True), 4)
        rows.append(
            {
                "profile": _text(raw.get("profile")) or "Unassigned profile",
                "dimension": _text(raw.get("dimension")) or "Unknown dimension",
                "baseline_weight": round(baseline, 4),
                "proposed_weight": round(proposed, 4),
                "weight_delta": delta,
                "affected_idea_count": _int(raw.get("affected_idea_count")),
                "average_score_delta": score_delta,
                "recommendation_change_count": changes,
                "rationale": _text(raw.get("rationale")),
                "risk_level": _risk(delta, changes),
            }
        )
    rows.sort(key=lambda row: (row["profile"].lower(), row["dimension"].lower()))
    return rows


def _profile_risks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles = sorted({row["profile"] for row in rows}, key=str.lower)
    output = []
    for profile in profiles:
        items = [row for row in rows if row["profile"] == profile]
        levels = [row["risk_level"] for row in items]
        risk = "high" if "high" in levels else "medium" if "medium" in levels else "low"
        output.append(
            {
                "profile": profile,
                "risk_level": risk,
                "dimension_count": len(items),
                "recommendation_change_count": sum(row["recommendation_change_count"] for row in items),
                "max_weight_delta": max(abs(row["weight_delta"]) for row in items),
            }
        )
    return output


def _risk(weight_delta: float, changes: int) -> str:
    if changes >= 3 or abs(weight_delta) >= 0.25:
        return "high"
    if changes > 0 or abs(weight_delta) >= 0.1:
        return "medium"
    return "low"


def _float(value: Any, *, signed: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if signed else max(0.0, number)


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
