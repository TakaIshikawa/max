"""Portfolio summary report for validation experiments."""

from __future__ import annotations

import json
from collections import Counter
from csv import DictWriter
from datetime import UTC, date, datetime
from io import StringIO
from typing import Any

from max.store.db import Store


COMPLETED_STATUSES = {"completed"}
FOLLOW_UP_STATUSES = {"blocked", "inconclusive"}
FOLLOW_UP_OUTCOMES = {"blocked", "inconclusive"}
VALIDATION_EXPERIMENT_SUMMARY_CSV_COLUMNS = [
    "filter_domain",
    "filter_idea_id",
    "filter_status",
    "filter_overdue_only",
    "row_type",
    "group",
    "key",
    "count",
    "value",
    "total_count",
    "completed_count",
    "overdue_count",
    "completion_rate",
    "average_confidence_delta",
    "average_result_score",
]


def _breakdown(counter: Counter[str]) -> list[dict]:
    return [
        {"key": key, "count": count}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


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


def _result_payload(experiment: dict) -> dict:
    raw = experiment.get("result_summary") or ""
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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


def _outcome(result: dict) -> str:
    value = result.get("outcome")
    return str(value).strip() if value else "unspecified"


def _follow_up_actions(result: dict) -> list[str]:
    actions: list[str] = []
    for key in ("follow_up_actions", "next_steps"):
        value = result.get(key)
        if isinstance(value, list):
            actions.extend(str(item).strip() for item in value if str(item).strip())
    value = result.get("follow_up_action")
    if value:
        actions.append(str(value).strip())
    return actions


def _is_overdue(experiment: dict, today: date) -> bool:
    due_date = _parse_date(experiment.get("due_date"))
    if due_date is None:
        return False
    return due_date < today and experiment.get("status") not in COMPLETED_STATUSES


def build_validation_experiment_summary(
    store: Store,
    *,
    domain: str | None = None,
    idea_id: str | None = None,
    status: str | None = None,
    overdue_only: bool = False,
    today: date | None = None,
) -> dict:
    """Build aggregate validation experiment counts and grouped breakdowns."""
    current_date = today or datetime.now(UTC).date()
    experiments = store.query_validation_experiments(
        domain=domain,
        idea_id=idea_id,
        status=status,
    )
    if overdue_only:
        experiments = [
            experiment
            for experiment in experiments
            if _is_overdue(experiment, current_date)
        ]

    status_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    follow_up_counts: Counter[str] = Counter()
    confidence_values: list[float] = []
    result_score_values: list[float] = []
    completed_count = 0
    overdue_count = 0

    for experiment in experiments:
        result = _result_payload(experiment)
        experiment_status = str(experiment.get("status") or "unspecified")
        outcome = _outcome(result)

        status_counts[experiment_status] += 1
        domain_counts[str(experiment.get("domain") or "unspecified")] += 1
        type_counts[str(experiment.get("method") or "unspecified")] += 1
        outcome_counts[outcome] += 1

        if experiment_status in COMPLETED_STATUSES:
            completed_count += 1
        if _is_overdue(experiment, current_date):
            overdue_count += 1

        confidence = _number(result.get("confidence_score"))
        if confidence is None:
            confidence = _number(result.get("confidence"))
        if confidence is None:
            confidence = _number(experiment.get("confidence_delta"))
        if confidence is not None:
            confidence_values.append(confidence)

        result_score = _number(result.get("result_score"))
        if result_score is None:
            result_score = _number(result.get("score"))
        if result_score is not None:
            result_score_values.append(result_score)

        if experiment_status in FOLLOW_UP_STATUSES or outcome in FOLLOW_UP_OUTCOMES:
            follow_up_counts.update(_follow_up_actions(result))

    total_count = len(experiments)
    completion_rate = round(completed_count / total_count, 3) if total_count else 0.0

    return {
        "filters": {
            "domain": domain,
            "idea_id": idea_id,
            "status": status,
            "overdue_only": overdue_only,
        },
        "total_count": total_count,
        "completed_count": completed_count,
        "overdue_count": overdue_count,
        "completion_rate": completion_rate,
        "average_confidence_delta": _average(confidence_values),
        "average_result_score": _average(result_score_values),
        "by_status": _breakdown(status_counts),
        "by_domain": _breakdown(domain_counts),
        "by_experiment_type": _breakdown(type_counts),
        "by_outcome": _breakdown(outcome_counts),
        "top_follow_up_actions": [
            {"action": action, "count": count}
            for action, count in sorted(
                follow_up_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:5]
        ],
    }


def render_validation_experiment_summary_csv(summary: dict[str, Any]) -> str:
    """Render a validation experiment summary as deterministic CSV."""
    output = StringIO()
    writer = DictWriter(
        output,
        fieldnames=VALIDATION_EXPERIMENT_SUMMARY_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _validation_experiment_summary_csv_rows(summary):
        writer.writerow(row)
    return output.getvalue()


def _validation_experiment_summary_csv_rows(summary: dict[str, Any]) -> list[dict[str, str]]:
    rows = [
        _validation_experiment_summary_csv_row(
            summary,
            row_type="overall",
            group="summary",
            key="all",
            count=summary.get("total_count"),
            total_count=summary.get("total_count"),
            completed_count=summary.get("completed_count"),
            overdue_count=summary.get("overdue_count"),
            completion_rate=summary.get("completion_rate"),
            average_confidence_delta=summary.get("average_confidence_delta"),
            average_result_score=summary.get("average_result_score"),
        )
    ]

    for metric in ("average_confidence_delta", "average_result_score"):
        value = summary.get(metric)
        if value is not None:
            rows.append(
                _validation_experiment_summary_csv_row(
                    summary,
                    row_type="average",
                    group="metrics",
                    key=metric,
                    value=value,
                )
            )

    for group, summary_key in (
        ("status", "by_status"),
        ("domain", "by_domain"),
        ("experiment_type", "by_experiment_type"),
        ("outcome", "by_outcome"),
    ):
        for item in summary.get(summary_key) or []:
            rows.append(
                _validation_experiment_summary_csv_row(
                    summary,
                    row_type="breakdown",
                    group=group,
                    key=item.get("key"),
                    count=item.get("count"),
                )
            )

    for item in summary.get("top_follow_up_actions") or []:
        rows.append(
            _validation_experiment_summary_csv_row(
                summary,
                row_type="follow_up_action",
                group="top_follow_up_actions",
                key=item.get("action"),
                count=item.get("count"),
            )
        )

    return rows


def _validation_experiment_summary_csv_row(
    summary: dict[str, Any],
    **values: Any,
) -> dict[str, str]:
    filters = summary.get("filters") or {}
    row = {
        "filter_domain": filters.get("domain"),
        "filter_idea_id": filters.get("idea_id"),
        "filter_status": filters.get("status"),
        "filter_overdue_only": filters.get("overdue_only"),
    }
    row.update(values)
    return {
        column: _validation_experiment_summary_csv_text(row.get(column))
        for column in VALIDATION_EXPERIMENT_SUMMARY_CSV_COLUMNS
    }


def _validation_experiment_summary_csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
