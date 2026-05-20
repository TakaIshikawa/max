from __future__ import annotations

import csv
import json
from datetime import date
from io import StringIO

import pytest

from max.analysis.validation_experiment_backlog_report import (
    KIND,
    SCHEMA_VERSION,
    build_validation_experiment_backlog_report,
    render_validation_experiment_backlog_report,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_validation_experiment_backlog_ranks_blocked_overdue_pending(store: Store) -> None:
    _seed_experiments(store)

    report = build_validation_experiment_backlog_report(store, today=date(2026, 5, 20))
    repeated = build_validation_experiment_backlog_report(store, today=date(2026, 5, 20))

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert set(report) == {
        "schema_version",
        "kind",
        "filters",
        "summary",
        "status_bands",
        "experiments",
        "next_actions",
    }
    assert [row["id"] for row in report["experiments"]] == ["vexp-blocked", "vexp-overdue", "vexp-pending", "vexp-running", "vexp-done"]
    assert report["status_bands"]["blocked"] == ["vexp-blocked"]
    assert report["status_bands"]["overdue"] == ["vexp-overdue"]
    assert report["summary"]["blocked_count"] == 1
    assert report["summary"]["overdue_count"] == 1
    assert "missing target metric" in report["experiments"][0]["rank_reason"]


def test_validation_experiment_backlog_filters_with_store_query(store: Store) -> None:
    _seed_experiments(store)

    by_status = build_validation_experiment_backlog_report(store, status="planned", today=date(2026, 5, 20))
    by_idea = build_validation_experiment_backlog_report(store, idea_id="idea-one", today=date(2026, 5, 20))

    assert [row["id"] for row in by_status["experiments"]] == ["vexp-overdue", "vexp-pending"]
    assert {row["idea_id"] for row in by_idea["experiments"]} == {"idea-one"}


def test_validation_experiment_backlog_renders_and_validates(store: Store) -> None:
    _seed_experiments(store)
    report = build_validation_experiment_backlog_report(store, today=date(2026, 5, 20))

    assert json.loads(render_validation_experiment_backlog_report(report, fmt="json")) == report
    markdown = render_validation_experiment_backlog_report(report, fmt="markdown")
    assert markdown.startswith("# Validation Experiment Backlog")
    rows = list(csv.DictReader(StringIO(render_validation_experiment_backlog_report(report, fmt="csv"))))
    assert rows[0]["id"] == "vexp-blocked"

    with pytest.raises(ValueError, match="Unsupported validation experiment backlog report format: yaml"):
        render_validation_experiment_backlog_report(report, fmt="yaml")


def _seed_experiments(store: Store) -> None:
    store.insert_buildable_unit(_unit("idea-one", "analytics"))
    store.insert_buildable_unit(_unit("idea-two", "security"))
    _experiment(store, "vexp-blocked", "idea-one", "blocked", "2026-05-01T00:00:00+00:00", "2026-05-25", "")
    _experiment(store, "vexp-overdue", "idea-two", "planned", "2026-05-02T00:00:00+00:00", "2026-05-10", "5 interviews")
    _experiment(store, "vexp-pending", "idea-one", "planned", "2026-05-04T00:00:00+00:00", "2026-05-30", "10 signups")
    _experiment(store, "vexp-running", "idea-two", "running", "2026-05-03T00:00:00+00:00", "2026-05-30", "3 pilots")
    _experiment(store, "vexp-done", "idea-two", "completed", "2026-05-01T00:00:00+00:00", "2026-05-05", "complete")


def _experiment(
    store: Store,
    experiment_id: str,
    idea_id: str,
    status: str,
    created_at: str,
    due_date: str,
    success_metric: str,
) -> None:
    created = store.create_validation_experiment(
        idea_id,
        hypothesis=f"{experiment_id} hypothesis",
        method="interview",
        success_metric=success_metric,
        status=status,
        due_date=due_date,
    )
    assert created is not None
    store.conn.execute(
        "UPDATE validation_experiments SET id = ?, created_at = ?, updated_at = ? WHERE id = ?",
        (experiment_id, created_at, created_at, created["id"]),
    )
    store._commit()


def _unit(idea_id: str, domain: str) -> BuildableUnit:
    return BuildableUnit(
        id=idea_id,
        title=idea_id,
        one_liner="one",
        category=BuildableCategory.APPLICATION,
        problem="problem",
        solution="solution",
        value_proposition="value",
        domain=domain,
        status="approved",
    )
