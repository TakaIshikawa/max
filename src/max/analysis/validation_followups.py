"""Recommend follow-up actions for an idea's validation experiments."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from typing import Any

from max.store.db import Store


COMPLETED_STATUSES = {"completed"}
ACTIVE_STATUSES = {"planned", "running", "blocked", "inconclusive"}
FOLLOW_UP_ACTIONS = {"continue", "pivot", "scale", "schedule_followup", "archive"}


def build_validation_followups(
    store: Store,
    idea_id: str,
    *,
    today: date | None = None,
) -> dict | None:
    """Build ranked validation follow-up recommendations for an idea."""
    if store.get_buildable_unit(idea_id) is None:
        return None

    current_date = today or datetime.now(UTC).date()
    experiments = store.list_validation_experiments(idea_id) or []
    latest = _latest_experiment(experiments)
    status_counts = Counter(
        str(experiment.get("status") or "unspecified") for experiment in experiments
    )
    evidence_url_count = sum(
        len(experiment.get("evidence_urls") or []) for experiment in experiments
    )
    deltas = [
        delta
        for delta in (_number(experiment.get("confidence_delta")) for experiment in experiments)
        if delta is not None
    ]
    actions = _recommend_actions(experiments, current_date)

    return {
        "idea_id": idea_id,
        "total_count": len(experiments),
        "latest_experiment": latest,
        "status_counts": _breakdown(status_counts),
        "evidence_url_count": evidence_url_count,
        "confidence_delta_summary": _confidence_delta_summary(deltas, latest),
        "follow_up_actions": [
            {
                "rank": index,
                "action": item["action"],
                "reason": item["reason"],
                "experiment_id": item.get("experiment_id"),
            }
            for index, item in enumerate(_rank_actions(actions), start=1)
        ],
    }


def _recommend_actions(experiments: list[dict], today: date) -> list[dict]:
    if not experiments:
        return [
            {
                "action": "schedule_followup",
                "reason": (
                    "No validation experiments are recorded; "
                    "schedule the first validation step."
                ),
                "priority": 80,
                "experiment_id": None,
            }
        ]

    actions: list[dict] = []
    overdue = [experiment for experiment in experiments if _is_overdue(experiment, today)]
    if overdue:
        sample = overdue[0]
        actions.append(
            {
                "action": "schedule_followup",
                "reason": (
                    f"{len(overdue)} active validation experiment"
                    f"{'' if len(overdue) == 1 else 's'} overdue; reset owner, scope, or due date."
                ),
                "priority": 95,
                "experiment_id": sample["id"],
            }
        )

    completed = [
        experiment for experiment in experiments if _status(experiment) in COMPLETED_STATUSES
    ]
    negative = [
        experiment
        for experiment in completed
        if (_number(experiment.get("confidence_delta")) or 0.0) < 0
    ]
    positive_with_evidence = [
        experiment
        for experiment in completed
        if (_number(experiment.get("confidence_delta")) or 0.0) > 0
        and len(experiment.get("evidence_urls") or []) > 0
    ]

    if negative:
        avg_negative = _average(
            [
                delta
                for delta in (
                    _number(experiment.get("confidence_delta")) for experiment in negative
                )
                if delta is not None
            ]
        )
        action = (
            "archive"
            if avg_negative is not None and avg_negative <= -0.35 and not positive_with_evidence
            else "pivot"
        )
        actions.append(
            {
                "action": action,
                "reason": _negative_reason(action, negative, avg_negative),
                "priority": 90 if action == "archive" else 88,
                "experiment_id": negative[0]["id"],
            }
        )

    if positive_with_evidence:
        avg_positive = _average(
            [
                delta
                for delta in (
                    _number(experiment.get("confidence_delta"))
                    for experiment in positive_with_evidence
                )
                if delta is not None
            ]
        )
        evidence_count = sum(
            len(experiment.get("evidence_urls") or []) for experiment in positive_with_evidence
        )
        action = (
            "scale"
            if avg_positive is not None and avg_positive >= 0.25 and evidence_count >= 2
            else "continue"
        )
        actions.append(
            {
                "action": action,
                "reason": _positive_reason(
                    action,
                    positive_with_evidence,
                    avg_positive,
                    evidence_count,
                ),
                "priority": 82 if action == "scale" else 75,
                "experiment_id": positive_with_evidence[0]["id"],
            }
        )

    if not actions:
        active_count = sum(
            1 for experiment in experiments if _status(experiment) in ACTIVE_STATUSES
        )
        experiment_count = active_count or len(experiments)
        actions.append(
            {
                "action": "continue",
                "reason": (
                    f"{experiment_count} validation experiment"
                    f"{'' if experiment_count == 1 else 's'} need more outcome evidence "
                    "before changing direction."
                ),
                "priority": 50,
                "experiment_id": experiments[0]["id"],
            }
        )

    return actions


def _rank_actions(actions: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for action in actions:
        name = action["action"]
        if name not in FOLLOW_UP_ACTIONS:
            continue
        current = deduped.get(name)
        if current is None or (action["priority"], action["reason"]) > (
            current["priority"],
            current["reason"],
        ):
            deduped[name] = action
    return sorted(
        deduped.values(),
        key=lambda item: (-int(item["priority"]), str(item["action"]), str(item["reason"])),
    )


def _latest_experiment(experiments: list[dict]) -> dict | None:
    if not experiments:
        return None
    return sorted(
        experiments,
        key=lambda experiment: (
            _date_key(experiment.get("completed_at")),
            _date_key(experiment.get("updated_at")),
            _date_key(experiment.get("created_at")),
            str(experiment.get("id") or ""),
        ),
        reverse=True,
    )[0]


def _confidence_delta_summary(deltas: list[float], latest: dict | None) -> dict:
    return {
        "count": len(deltas),
        "positive_count": sum(1 for delta in deltas if delta > 0),
        "negative_count": sum(1 for delta in deltas if delta < 0),
        "neutral_count": sum(1 for delta in deltas if delta == 0),
        "total": round(sum(deltas), 3) if deltas else 0.0,
        "average": _average(deltas),
        "latest": _number(latest.get("confidence_delta")) if latest else None,
    }


def _breakdown(counter: Counter[str]) -> list[dict]:
    return [
        {"key": key, "count": count}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _negative_reason(action: str, experiments: list[dict], avg_negative: float | None) -> str:
    summary = _summary_text(experiments[0])
    delta = (
        f"average confidence delta {avg_negative:.3f}"
        if avg_negative is not None
        else "negative confidence delta"
    )
    if action == "archive":
        return (
            f"Completed validation is strongly negative ({delta}); archive unless new "
            f"evidence changes the premise. {summary}"
        )
    return (
        f"Completed validation reduced confidence ({delta}); pivot the hypothesis or "
        f"target segment. {summary}"
    )


def _positive_reason(
    action: str,
    experiments: list[dict],
    avg_positive: float | None,
    evidence_count: int,
) -> str:
    delta = (
        f"average confidence delta {avg_positive:.3f}"
        if avg_positive is not None
        else "positive confidence delta"
    )
    if action == "scale":
        return (
            "Completed validation has evidence-backed upside "
            f"({delta}, {evidence_count} evidence URLs); scale the test."
        )
    return (
        "Completed validation is positive with evidence "
        f"({delta}, {evidence_count} evidence URLs); continue validation."
    )


def _summary_text(experiment: dict) -> str:
    summary = str(experiment.get("result_summary") or "").strip()
    if not summary:
        return ""
    payload = _result_payload(summary)
    if payload:
        outcome = payload.get("outcome")
        if outcome:
            return f"Outcome: {outcome}."
    return f"Result: {summary[:160]}."


def _result_payload(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_overdue(experiment: dict, today: date) -> bool:
    due_date = _parse_date(experiment.get("due_date"))
    return (
        due_date is not None
        and due_date < today
        and _status(experiment) not in COMPLETED_STATUSES
    )


def _status(experiment: dict) -> str:
    return str(experiment.get("status") or "").strip().lower()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(text)
            except ValueError:
                return None
    return None


def _date_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
