"""Tests for validation experiment portfolio summaries."""

from __future__ import annotations

import csv
import json
from datetime import date
from io import StringIO

from max.analysis.validation_experiment_summary import (
    VALIDATION_EXPERIMENT_SUMMARY_CSV_COLUMNS,
    build_validation_experiment_summary,
    render_validation_experiment_summary_csv,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


def _unit(unit_id: str, domain: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"{domain} validation idea",
        one_liner="Summarize validation experiments",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Experiment tracking is hard to prioritize",
        solution="Aggregate experiment outcomes",
        value_proposition="Make validation work portfolio-readable",
        domain=domain,
    )


def _seed(store: Store) -> None:
    store.insert_buildable_unit(_unit("bu-summary-devtools", "devtools"))
    store.insert_buildable_unit(_unit("bu-summary-aiops", "aiops"))

    store.create_validation_experiment(
        "bu-summary-devtools",
        hypothesis="Developers will use the prototype",
        method="prototype",
        success_metric="7 of 10 activate",
        status="completed",
        due_date="2026-04-20",
        completed_at="2026-04-21T00:00:00+00:00",
        result_summary=json.dumps(
            {"outcome": "validated", "result_score": 0.8, "confidence_score": 0.7}
        ),
        confidence_delta=0.3,
    )
    store.create_validation_experiment(
        "bu-summary-devtools",
        hypothesis="Buyers will approve budget",
        method="interview",
        success_metric="3 budget owners commit",
        status="blocked",
        due_date="2026-04-23",
        result_summary=json.dumps(
            {
                "outcome": "blocked",
                "follow_up_actions": ["recruit budget owners", "tighten ICP"],
            }
        ),
    )
    store.create_validation_experiment(
        "bu-summary-aiops",
        hypothesis="Operators can complete setup",
        method="survey",
        success_metric="80 percent report confidence",
        status="running",
        due_date="2999-01-01",
        result_summary=json.dumps(
            {
                "outcome": "inconclusive",
                "result_score": 0.4,
                "follow_up_action": "recruit budget owners",
            }
        ),
        confidence_delta=0.1,
    )


def _counts(items: list[dict]) -> dict[str, int]:
    return {item["key"]: item["count"] for item in items}


def test_validation_experiment_summary_aggregates_counts_and_metrics(store: Store) -> None:
    _seed(store)

    report = build_validation_experiment_summary(store, today=date(2026, 4, 24))

    assert report["total_count"] == 3
    assert report["completed_count"] == 1
    assert report["overdue_count"] == 1
    assert report["completion_rate"] == 0.333
    assert report["average_confidence_delta"] == 0.4
    assert report["average_result_score"] == 0.6
    assert _counts(report["by_status"]) == {"blocked": 1, "completed": 1, "running": 1}
    assert _counts(report["by_domain"]) == {"devtools": 2, "aiops": 1}
    assert _counts(report["by_experiment_type"]) == {"interview": 1, "prototype": 1, "survey": 1}
    assert _counts(report["by_outcome"]) == {"blocked": 1, "inconclusive": 1, "validated": 1}
    assert report["top_follow_up_actions"] == [
        {"action": "recruit budget owners", "count": 2},
        {"action": "tighten ICP", "count": 1},
    ]


def test_validation_experiment_summary_filters_are_deterministic(store: Store) -> None:
    _seed(store)

    domain_report = build_validation_experiment_summary(
        store,
        domain="devtools",
        today=date(2026, 4, 24),
    )
    idea_report = build_validation_experiment_summary(
        store,
        idea_id="bu-summary-aiops",
        today=date(2026, 4, 24),
    )
    status_report = build_validation_experiment_summary(
        store,
        status="blocked",
        today=date(2026, 4, 24),
    )
    overdue_report = build_validation_experiment_summary(
        store,
        overdue_only=True,
        today=date(2026, 4, 24),
    )

    assert domain_report["total_count"] == 2
    assert _counts(domain_report["by_domain"]) == {"devtools": 2}
    assert idea_report["total_count"] == 1
    assert _counts(idea_report["by_status"]) == {"running": 1}
    assert status_report["total_count"] == 1
    assert _counts(status_report["by_status"]) == {"blocked": 1}
    assert overdue_report["total_count"] == 1
    assert overdue_report["overdue_count"] == 1
    assert _counts(overdue_report["by_status"]) == {"blocked": 1}


def test_validation_experiment_summary_empty_report_is_well_formed(store: Store) -> None:
    _seed(store)

    report = build_validation_experiment_summary(store, domain="missing")

    assert report == {
        "filters": {
            "domain": "missing",
            "idea_id": None,
            "status": None,
            "overdue_only": False,
        },
        "total_count": 0,
        "completed_count": 0,
        "overdue_count": 0,
        "completion_rate": 0.0,
        "average_confidence_delta": None,
        "average_result_score": None,
        "by_status": [],
        "by_domain": [],
        "by_experiment_type": [],
        "by_outcome": [],
        "top_follow_up_actions": [],
    }


def test_render_validation_experiment_summary_csv_is_deterministic(store: Store) -> None:
    _seed(store)
    report = build_validation_experiment_summary(store, today=date(2026, 4, 24))

    csv_text = render_validation_experiment_summary_csv(report)
    repeated = render_validation_experiment_summary_csv(report)
    reader = csv.DictReader(StringIO(csv_text))
    rows = list(reader)

    assert csv_text == repeated
    assert reader.fieldnames == VALIDATION_EXPERIMENT_SUMMARY_CSV_COLUMNS
    assert csv_text.splitlines()[0] == ",".join(VALIDATION_EXPERIMENT_SUMMARY_CSV_COLUMNS)
    assert rows[0] == {
        "filter_domain": "",
        "filter_idea_id": "",
        "filter_status": "",
        "filter_overdue_only": "false",
        "row_type": "overall",
        "group": "summary",
        "key": "all",
        "count": "3",
        "value": "",
        "total_count": "3",
        "completed_count": "1",
        "overdue_count": "1",
        "completion_rate": "0.333",
        "average_confidence_delta": "0.4",
        "average_result_score": "0.6",
    }
    assert rows[1:3] == [
        {
            "filter_domain": "",
            "filter_idea_id": "",
            "filter_status": "",
            "filter_overdue_only": "false",
            "row_type": "average",
            "group": "metrics",
            "key": "average_confidence_delta",
            "count": "",
            "value": "0.4",
            "total_count": "",
            "completed_count": "",
            "overdue_count": "",
            "completion_rate": "",
            "average_confidence_delta": "",
            "average_result_score": "",
        },
        {
            "filter_domain": "",
            "filter_idea_id": "",
            "filter_status": "",
            "filter_overdue_only": "false",
            "row_type": "average",
            "group": "metrics",
            "key": "average_result_score",
            "count": "",
            "value": "0.6",
            "total_count": "",
            "completed_count": "",
            "overdue_count": "",
            "completion_rate": "",
            "average_confidence_delta": "",
            "average_result_score": "",
        },
    ]
    assert [
        (row["row_type"], row["group"], row["key"], row["count"])
        for row in rows[3:]
    ] == [
        ("breakdown", "status", "blocked", "1"),
        ("breakdown", "status", "completed", "1"),
        ("breakdown", "status", "running", "1"),
        ("breakdown", "domain", "devtools", "2"),
        ("breakdown", "domain", "aiops", "1"),
        ("breakdown", "experiment_type", "interview", "1"),
        ("breakdown", "experiment_type", "prototype", "1"),
        ("breakdown", "experiment_type", "survey", "1"),
        ("breakdown", "outcome", "blocked", "1"),
        ("breakdown", "outcome", "inconclusive", "1"),
        ("breakdown", "outcome", "validated", "1"),
        ("follow_up_action", "top_follow_up_actions", "recruit budget owners", "2"),
        ("follow_up_action", "top_follow_up_actions", "tighten ICP", "1"),
    ]
    assert all(
        row["filter_domain"] == ""
        and row["filter_idea_id"] == ""
        and row["filter_status"] == ""
        and row["filter_overdue_only"] == "false"
        for row in rows
    )


def test_render_validation_experiment_summary_csv_preserves_filter_context(
    store: Store,
) -> None:
    _seed(store)
    report = build_validation_experiment_summary(
        store,
        domain="devtools",
        status="blocked",
        overdue_only=True,
        today=date(2026, 4, 24),
    )

    rows = list(
        csv.DictReader(StringIO(render_validation_experiment_summary_csv(report)))
    )

    assert rows
    assert all(
        row["filter_domain"] == "devtools"
        and row["filter_idea_id"] == ""
        and row["filter_status"] == "blocked"
        and row["filter_overdue_only"] == "true"
        for row in rows
    )
    assert rows[0]["total_count"] == "1"
    assert ("breakdown", "status", "blocked", "1") in [
        (row["row_type"], row["group"], row["key"], row["count"]) for row in rows
    ]


def test_render_validation_experiment_summary_csv_empty_summary_has_overall_row(
    store: Store,
) -> None:
    _seed(store)
    report = build_validation_experiment_summary(store, domain="missing")

    csv_text = render_validation_experiment_summary_csv(report)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text.splitlines()[0] == ",".join(VALIDATION_EXPERIMENT_SUMMARY_CSV_COLUMNS)
    assert rows == [
        {
            "filter_domain": "missing",
            "filter_idea_id": "",
            "filter_status": "",
            "filter_overdue_only": "false",
            "row_type": "overall",
            "group": "summary",
            "key": "all",
            "count": "0",
            "value": "",
            "total_count": "0",
            "completed_count": "0",
            "overdue_count": "0",
            "completion_rate": "0.0",
            "average_confidence_delta": "",
            "average_result_score": "",
        }
    ]
