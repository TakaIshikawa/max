"""Profile coverage drift export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.profile_coverage_drift_report.v1"
KIND = "max.profile_coverage_drift_report"


class ProfileCoverageDriftInput(TypedDict, total=False):
    profile: str
    category: str
    source: str
    target_user: str
    expected_count: int | float | str
    observed_count: int | float | str
    expected_weight: int | float | str
    observed_weight: int | float | str


def build_profile_coverage_drift_report(records: Iterable[ProfileCoverageDriftInput | dict[str, Any]], *, title: str = "Profile Coverage Drift Report") -> dict[str, Any]:
    rows = [_row(raw, index) for index, raw in enumerate(records)]
    rows.sort(key=lambda row: (-row["gap_severity_score"], row["profile"].lower(), row["category"].lower(), row["source"].lower(), row["target_user"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "title": _text(title) or "Profile Coverage Drift Report", "summary": {"coverage_slice_count": len(rows), "severe_gap_count": sum(1 for row in rows if row["severity"] == "high")}, "coverage_gaps": rows, "category_gaps": _totals(rows, "category"), "source_gaps": _totals(rows, "source"), "target_user_gaps": _totals(rows, "target_user"), "allocation_adjustments": [_adjustment(row) for row in rows if row["gap"] > 0]}


def render_profile_coverage_drift_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Profile Coverage Drift Report'}", "", "## Drift Severity", ""]
    gaps = report.get("coverage_gaps") or []
    if not gaps:
        lines.append("- No profile coverage records supplied.")
    else:
        for row in gaps[:10]:
            lines.append(f"- {row['profile']} {row['category']} / {row['source']} / {row['target_user']}: {row['severity']} gap {row['gap']}")
    lines.extend(["", "## Suggested Allocation Adjustments", ""])
    lines.extend([f"- {item}" for item in report.get("allocation_adjustments") or []] or ["- No allocation adjustment needed."])
    return "\n".join(lines).rstrip() + "\n"


def render_profile_coverage_drift_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    expected = _int(raw.get("expected_count"))
    observed = _int(raw.get("observed_count"))
    expected_weight = _float(raw.get("expected_weight"), 1.0)
    observed_weight = _float(raw.get("observed_weight"), 0.0 if "observed_weight" in raw else expected_weight)
    gap = max(expected - observed, 0)
    weight_gap = max(expected_weight - observed_weight, 0.0)
    score = round(gap + weight_gap * 10, 4)
    return {"profile": _text(raw.get("profile")) or "Unassigned profile", "category": _text(raw.get("category")) or f"category-{index + 1}", "source": _text(raw.get("source")) or "Unspecified source", "target_user": _text(raw.get("target_user") or raw.get("user")) or "Unspecified user", "expected_count": expected, "observed_count": observed, "gap": gap, "expected_weight": expected_weight, "observed_weight": observed_weight, "weight_gap": round(weight_gap, 4), "gap_severity_score": score, "severity": "high" if score >= 5 else ("medium" if score >= 1 else "low")}


def _totals(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    values = sorted({row[key] for row in rows}, key=str.lower)
    return [{key: value, "expected_count": sum(row["expected_count"] for row in rows if row[key] == value), "observed_count": sum(row["observed_count"] for row in rows if row[key] == value), "gap": sum(row["gap"] for row in rows if row[key] == value)} for value in values]


def _adjustment(row: dict[str, Any]) -> str:
    return f"Allocate {row['gap']} more signals or ideas to {row['profile']} {row['category']} for {row['target_user']}."


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return round(max(0.0, float(value)), 4)
    except (TypeError, ValueError):
        return default


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
