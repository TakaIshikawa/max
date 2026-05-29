"""Evaluation rubric drift remediation export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.evaluation_rubric_drift_remediation_report.v1"
KIND = "max.evaluation_rubric_drift_remediation_report"


def generate_evaluation_rubric_drift_remediation_report(
    records: Iterable[dict[str, Any]],
    *,
    drift_threshold: float = 0.15,
    title: str = "Evaluation Rubric Drift Remediation Report",
) -> dict[str, Any]:
    threshold = _threshold(drift_threshold)
    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(_group)
    for raw in records:
        if not isinstance(raw, dict):
            continue
        key = (
            _text(raw.get("profile") or raw.get("profile_id")) or "unknown-profile",
            _text(raw.get("rubric_version") or raw.get("version")) or "unknown-version",
            _text(raw.get("dimension") or raw.get("rubric_dimension")) or "unknown-dimension",
        )
        group = groups[key]
        group["baseline"].append(_score(raw.get("baseline_score") or raw.get("expected_score")))
        group["current"].append(_score(raw.get("current_score") or raw.get("observed_score") or raw.get("score")))

    rows = [_row(*key, group, threshold) for key, group in groups.items()]
    rows.sort(key=lambda row: (_severity_rank(row["severity"]), -row["absolute_delta"], row["profile"].lower(), row["rubric_version"].lower(), row["dimension"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Evaluation Rubric Drift Remediation Report",
        "summary": {
            "row_count": len(rows),
            "drift_threshold": threshold,
            "drifted_row_count": sum(1 for row in rows if row["absolute_delta"] > threshold),
            "critical_row_count": sum(1 for row in rows if row["severity"] == "critical"),
            "stable_row_count": sum(1 for row in rows if row["severity"] == "low"),
        },
        "rows": rows,
    }


def render_evaluation_rubric_drift_remediation_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_evaluation_rubric_drift_remediation_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Evaluation Rubric Drift Remediation Report'}",
        "",
        "## Summary",
        "",
        f"- Rows: {summary.get('row_count', 0)}",
        f"- Drift threshold: {summary.get('drift_threshold', 0.0)}",
        f"- Drifted rows: {summary.get('drifted_row_count', 0)}",
        "",
        "## Drift Rows",
        "",
    ]
    rows = report.get("rows") or []
    if not rows:
        lines.append("- No evaluation rubric drift detected.")
    else:
        for row in rows:
            lines.append(
                f"- {row['profile']} / {row['rubric_version']} / {row['dimension']}: "
                f"{row['baseline_score']} -> {row['current_score']} "
                f"(delta {row['absolute_delta']}, {row['severity']}) - {row['recommended_action']}"
            )
    return "\n".join(lines).rstrip() + "\n"


def _group() -> dict[str, list[float]]:
    return {"baseline": [], "current": []}


def _row(profile: str, version: str, dimension: str, group: dict[str, list[float]], threshold: float) -> dict[str, Any]:
    baseline = _avg(group["baseline"])
    current = _avg(group["current"])
    delta = round(abs(current - baseline), 4)
    severity = _severity(delta, threshold)
    return {
        "profile": profile,
        "rubric_version": version,
        "dimension": dimension,
        "sample_count": len(group["current"]),
        "baseline_score": baseline,
        "current_score": current,
        "absolute_delta": delta,
        "severity": severity,
        "recommended_action": _action(severity),
    }


def _severity(delta: float, threshold: float) -> str:
    if delta >= threshold * 3:
        return "critical"
    if delta >= threshold * 2:
        return "high"
    if delta > threshold:
        return "medium"
    return "low"


def _action(severity: str) -> str:
    return {
        "critical": "Pause dependent releases and recalibrate rubric anchors with evaluator review.",
        "high": "Schedule rubric calibration and inspect recent evaluator disagreements.",
        "medium": "Review dimension examples and refresh calibration notes.",
    }.get(severity, "Monitor in the next evaluation cycle.")


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _threshold(value: Any) -> float:
    try:
        return round(max(float(value), 0.0), 4)
    except (TypeError, ValueError):
        return 0.15


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
