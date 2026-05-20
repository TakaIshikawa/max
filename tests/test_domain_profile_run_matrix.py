from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from io import StringIO

import pytest

from max.analysis.domain_profile_run_matrix import (
    KIND,
    SCHEMA_VERSION,
    build_domain_profile_run_matrix,
    render_domain_profile_run_matrix,
)
from max.store.db import Store


def test_domain_profile_run_matrix_groups_and_flags_weak_cells(store: Store) -> None:
    _seed_runs(store)

    report = build_domain_profile_run_matrix(
        store,
        limit=10,
        now=datetime(2026, 5, 20, tzinfo=UTC),
        stale_after_days=7,
    )
    repeated = build_domain_profile_run_matrix(
        store,
        limit=10,
        now=datetime(2026, 5, 20, tzinfo=UTC),
        stale_after_days=7,
    )

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert set(report) == {
        "schema_version",
        "kind",
        "filters",
        "summary",
        "matrix",
        "weak_cells",
        "next_actions",
    }
    assert [(row["profile"], row["domain"]) for row in report["matrix"]] == [
        ("default", "security"),
        ("growth", "analytics"),
        ("growth", "security"),
    ]
    cells = {(row["profile"], row["domain"]): row for row in report["matrix"]}
    assert cells[("growth", "analytics")]["run_count"] == 2
    assert cells[("growth", "analytics")]["success_rate"] == 0.5
    assert cells[("growth", "analytics")]["average_ideas_generated"] == 0.5
    assert cells[("growth", "analytics")]["weak_reasons"] == ["low_success_rate", "low_idea_output"]
    assert cells[("default", "security")]["weak_reasons"] == ["stale_latest_run"]
    assert report["summary"]["weak_cell_count"] == 2


def test_domain_profile_run_matrix_renders_and_validates(store: Store) -> None:
    _seed_runs(store)
    report = build_domain_profile_run_matrix(store, now=datetime(2026, 5, 20, tzinfo=UTC))

    assert json.loads(render_domain_profile_run_matrix(report, fmt="json")) == report
    markdown = render_domain_profile_run_matrix(report, fmt="markdown")
    assert markdown.startswith("# Domain Profile Run Matrix")
    rows = list(csv.DictReader(StringIO(render_domain_profile_run_matrix(report, fmt="csv"))))
    assert rows[0]["profile"] == "default"

    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_domain_profile_run_matrix(store, limit=0)
    with pytest.raises(ValueError, match="min_success_rate must be between 0 and 1"):
        build_domain_profile_run_matrix(store, min_success_rate=1.5)
    with pytest.raises(ValueError, match="Unsupported domain profile run matrix format: yaml"):
        render_domain_profile_run_matrix(report, fmt="yaml")


def _seed_runs(store: Store) -> None:
    _run(store, "run-1", "growth", "analytics", "completed", 1, 70.0, "2026-05-19T00:00:00+00:00")
    _run(store, "run-2", "growth", "analytics", "failed", 0, 0.0, "2026-05-18T00:00:00+00:00")
    _run(store, "run-3", "growth", "security", "completed", 3, 82.0, "2026-05-17T00:00:00+00:00")
    _run(store, "run-4", "default", "security", "completed", 2, 75.0, "2026-04-01T00:00:00+00:00")


def _run(
    store: Store,
    run_id: str,
    profile: str,
    domain: str,
    status: str,
    ideas: int,
    score: float,
    started_at: str,
) -> None:
    store.insert_pipeline_run(run_id, {"profile": profile, "domain": domain})
    store.update_pipeline_run(run_id, ideas_generated=ideas, ideas_evaluated=ideas, avg_idea_score=score, status=status)
    store.insert_pipeline_run_domain(run_id, domain, {"ideas_generated": ideas, "ideas_evaluated": ideas, "avg_score": score})
    store.conn.execute(
        "UPDATE pipeline_runs SET started_at = ?, completed_at = ? WHERE id = ?",
        (started_at, started_at, run_id),
    )
    store._commit()
