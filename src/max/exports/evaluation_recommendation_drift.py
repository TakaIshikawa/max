"""Evaluation recommendation drift report export."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.evaluation_recommendation_drift.v1"
KIND = "max.evaluation_recommendation_drift"


class EvaluationRecommendationSnapshotInput(TypedDict, total=False):
    idea_id: str
    idea: str
    name: str
    evaluated_at: str
    recommendation: str
    score: float
    driver: str
    drift_driver: str
    reason: str


def build_evaluation_recommendation_drift_report(
    records: Iterable[EvaluationRecommendationSnapshotInput | dict[str, Any]],
    *,
    title: str = "Evaluation Recommendation Drift Report",
    large_drift_threshold: float = 0.2,
    top_driver_limit: int = 5,
) -> dict[str, Any]:
    snapshots = _normalize_snapshots(records)
    latest_by_idea = _latest_snapshots(snapshots)
    transitions = _transitions(snapshots, large_drift_threshold=large_drift_threshold)
    large_drifts = [transition for transition in transitions if transition["large_drift"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Evaluation Recommendation Drift Report",
        "large_drift_threshold": large_drift_threshold,
        "summary": {
            "snapshot_count": len(snapshots),
            "idea_count": len(latest_by_idea),
            "transition_count": len(transitions),
            "recommendation_change_count": sum(1 for transition in transitions if transition["changed"]),
            "large_drift_count": len(large_drifts),
            "average_score_delta": _average_delta(transitions),
        },
        "recommendation_distribution": _recommendation_distribution(latest_by_idea),
        "transition_counts": _transition_counts(transitions),
        "top_drift_drivers": _top_drift_drivers(transitions, limit=top_driver_limit),
        "large_drifts": large_drifts,
        "snapshots": snapshots,
    }


def render_evaluation_recommendation_drift_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Evaluation Recommendation Drift Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Ideas: {summary.get('idea_count', 0)}",
        f"- Snapshots: {summary.get('snapshot_count', 0)}",
        f"- Transitions: {summary.get('transition_count', 0)}",
        f"- Recommendation changes: {summary.get('recommendation_change_count', 0)}",
        f"- Average score delta: {summary.get('average_score_delta', 0.0)}",
        f"- Large drifts: {summary.get('large_drift_count', 0)}",
        "",
        "## Large Drifts",
        "",
    ]
    large_drifts = report.get("large_drifts") or []
    if large_drifts:
        for drift in large_drifts:
            lines.extend(
                [
                    f"### {drift['idea_id']} - {drift['idea']}",
                    "",
                    f"- Transition: {drift['previous_recommendation']} -> {drift['current_recommendation']}",
                    f"- Score delta: {drift['score_delta']}",
                    f"- Driver: {drift['driver']}",
                    f"- Current evaluation: {drift['current_evaluated_at'] or 'Unspecified'}",
                    "",
                ]
            )
    else:
        lines.append("- No large recommendation drifts were supplied.")
    return "\n".join(lines).rstrip() + "\n"


def render_evaluation_recommendation_drift_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_snapshots(records: Iterable[EvaluationRecommendationSnapshotInput | dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots = []
    for index, raw in enumerate(records):
        idea_id = _text(raw.get("idea_id") or raw.get("idea") or raw.get("name") or f"idea-{index + 1}")
        snapshots.append(
            {
                "idea_id": idea_id,
                "idea": _text(raw.get("idea") or raw.get("name") or idea_id),
                "evaluated_at": _text(raw.get("evaluated_at")),
                "recommendation": _recommendation(raw.get("recommendation")),
                "score": _number(raw.get("score")),
                "driver": _text(raw.get("drift_driver") or raw.get("driver") or raw.get("reason") or "Unspecified driver"),
            }
        )
    snapshots.sort(key=_snapshot_sort_key)
    return snapshots


def _latest_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        latest[snapshot["idea_id"]] = snapshot
    return sorted(latest.values(), key=lambda row: (row["recommendation"].lower(), row["idea_id"].lower()))


def _transitions(snapshots: list[dict[str, Any]], *, large_drift_threshold: float) -> list[dict[str, Any]]:
    by_idea: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        by_idea[snapshot["idea_id"]].append(snapshot)

    transitions = []
    for idea_id in sorted(by_idea):
        history = by_idea[idea_id]
        for previous, current in zip(history, history[1:]):
            delta = round(current["score"] - previous["score"], 4)
            changed = previous["recommendation"] != current["recommendation"]
            transitions.append(
                {
                    "idea_id": idea_id,
                    "idea": current["idea"],
                    "previous_evaluated_at": previous["evaluated_at"],
                    "current_evaluated_at": current["evaluated_at"],
                    "previous_recommendation": previous["recommendation"],
                    "current_recommendation": current["recommendation"],
                    "transition": f"{previous['recommendation']} -> {current['recommendation']}",
                    "previous_score": previous["score"],
                    "current_score": current["score"],
                    "score_delta": delta,
                    "absolute_score_delta": round(abs(delta), 4),
                    "changed": changed,
                    "large_drift": changed or abs(delta) >= large_drift_threshold,
                    "driver": current["driver"],
                }
            )
    transitions.sort(key=lambda row: (-row["absolute_score_delta"], row["current_evaluated_at"] or "", row["idea_id"].lower(), row["transition"].lower()))
    return transitions


def _recommendation_distribution(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(snapshot["recommendation"] for snapshot in snapshots)
    return [{"recommendation": recommendation, "count": count} for recommendation, count in sorted(counts.items(), key=lambda item: item[0].lower())]


def _transition_counts(transitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(transition["transition"] for transition in transitions)
    return [{"transition": transition, "count": count} for transition, count in sorted(counts.items(), key=lambda item: item[0].lower())]


def _top_drift_drivers(transitions: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    driver_transitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for transition in transitions:
        if transition["large_drift"]:
            driver_transitions[transition["driver"]].append(transition)
    rows = [
        {
            "driver": driver,
            "drift_count": len(items),
            "average_absolute_score_delta": round(sum(item["absolute_score_delta"] for item in items) / len(items), 4),
        }
        for driver, items in driver_transitions.items()
    ]
    rows.sort(key=lambda row: (-row["drift_count"], -row["average_absolute_score_delta"], row["driver"].lower()))
    return rows[: max(limit, 0)]


def _average_delta(transitions: list[dict[str, Any]]) -> float:
    if not transitions:
        return 0.0
    return round(sum(transition["score_delta"] for transition in transitions) / len(transitions), 4)


def _snapshot_sort_key(snapshot: dict[str, Any]) -> tuple[str, str, str]:
    return (snapshot["idea_id"].lower(), snapshot["evaluated_at"] or "", snapshot["recommendation"].lower())


def _recommendation(value: Any) -> str:
    return _text(value).lower().replace(" ", "_") or "unknown"


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
