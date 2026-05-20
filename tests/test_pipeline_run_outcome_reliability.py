"""Tests for pipeline run outcome reliability reports."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.pipeline_run_outcome_reliability import (
    KIND,
    SCHEMA_VERSION,
    build_pipeline_run_outcome_reliability,
    render_pipeline_run_outcome_reliability,
)
from max.store.db import Store


def test_pipeline_run_outcome_reliability_ranks_least_reliable_cohorts_first(store: Store) -> None:
    _seed_runs(store)

    report = build_pipeline_run_outcome_reliability(store, limit=10)
    repeated = build_pipeline_run_outcome_reliability(store, limit=10)

    assert report == repeated
    assert set(report) == {
        "schema_version",
        "kind",
        "filters",
        "summary",
        "cohorts",
        "status_bands",
        "next_actions",
    }
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"] == {
        "run_count": 5,
        "success_count": 2,
        "failure_count": 2,
        "cancelled_count": 1,
        "other_count": 0,
        "success_rate": 0.4,
        "failure_rate": 0.4,
        "cancelled_rate": 0.2,
        "cohort_count": 5,
        "repeated_failure_cohort_count": 2,
        "latest_run_started_at": "2026-05-05T00:00:00",
    }
    assert report["status_bands"] == {
        "success": ["run-healthy-2", "run-healthy-1"],
        "failure": ["run-fail-2", "run-fail-1"],
        "cancelled": ["run-cancelled"],
        "other": [],
    }
    assert [(row["cohort_type"], row["cohort"]) for row in report["cohorts"][:3]] == [
        ("domain", "finops"),
        ("profile", "growth"),
        ("domain", "support"),
    ]
    assert report["cohorts"][0]["failure_rate"] == 1.0
    assert report["cohorts"][0]["repeated_failure"] is True
    assert report["cohorts"][0]["latest_failure_run_id"] == "run-fail-2"
    assert report["cohorts"][-1]["cohort"] == "sales"
    assert any("Investigate repeated pipeline failures" in action for action in report["next_actions"])


def test_pipeline_run_outcome_reliability_empty_store_returns_guidance(store: Store) -> None:
    report = build_pipeline_run_outcome_reliability(store)

    assert report["cohorts"] == []
    assert report["summary"]["run_count"] == 0
    assert report["status_bands"] == {"success": [], "failure": [], "cancelled": [], "other": []}
    assert report["next_actions"] == [
        "Run the pipeline at least once before reviewing outcome reliability.",
        "Persist pipeline run status and error_message fields so failed cohorts can be triaged.",
    ]


def test_render_pipeline_run_outcome_reliability_json_markdown_csv_and_invalid_format(
    store: Store,
) -> None:
    _seed_runs(store)
    report = build_pipeline_run_outcome_reliability(store, limit=10)

    assert json.loads(render_pipeline_run_outcome_reliability(report, fmt="json")) == report

    markdown = render_pipeline_run_outcome_reliability(report, fmt="markdown")
    assert markdown.startswith("# Pipeline Run Outcome Reliability")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Cohorts" in markdown
    assert "| `domain` | `finops` | failing | 2 | 0.000 | 1.000 | 0.000 |" in markdown

    rendered_csv = render_pipeline_run_outcome_reliability(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert rendered_csv.splitlines()[0] == (
        "cohort_type,cohort,run_count,success_count,failure_count,cancelled_count,"
        "other_count,success_rate,failure_rate,cancelled_rate,reliability_band,"
        "latest_failure_run_id,latest_failure_at,latest_error"
    )
    assert [(row["cohort_type"], row["cohort"]) for row in rows[:2]] == [
        ("domain", "finops"),
        ("profile", "growth"),
    ]
    assert rows[0]["latest_error"] == "worker crashed"

    with pytest.raises(ValueError, match="Unsupported pipeline run outcome reliability format: yaml"):
        render_pipeline_run_outcome_reliability(report, fmt="yaml")
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_pipeline_run_outcome_reliability(store, limit=0)


def _seed_runs(store: Store) -> None:
    _insert_run(store, "run-healthy-1", "completed", "growth", "sales", "2026-05-01T00:00:00")
    _insert_run(store, "run-fail-1", "failed", "growth", "finops", "2026-05-02T00:00:00", "timeout")
    _insert_run(store, "run-cancelled", "cancelled", "ops", "support", "2026-05-03T00:00:00")
    _insert_run(store, "run-fail-2", "error", "growth", "finops", "2026-05-04T00:00:00", "worker crashed")
    _insert_run(store, "run-healthy-2", "completed", "ops", "support", "2026-05-05T00:00:00")


def _insert_run(
    store: Store,
    run_id: str,
    status: str,
    profile: str,
    domain: str,
    started_at: str,
    error: str = "",
) -> None:
    store.insert_pipeline_run(run_id, {"profile": profile, "domain": domain})
    store.update_pipeline_run(run_id, status=status, error_message=error)
    store.conn.execute(
        "UPDATE pipeline_runs SET started_at = ?, completed_at = ? WHERE id = ?",
        (started_at, started_at, run_id),
    )
    store._commit()
