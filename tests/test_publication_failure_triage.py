from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.publication_failure_triage import (
    KIND,
    SCHEMA_VERSION,
    build_publication_failure_triage,
    render_publication_failure_triage,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_publication_failure_triage_prioritizes_open_failures(store: Store) -> None:
    _seed_publications(store)

    report = build_publication_failure_triage(store)
    repeated = build_publication_failure_triage(store)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert set(report) == {
        "schema_version",
        "kind",
        "filters",
        "summary",
        "failure_groups",
        "affected_ideas",
        "next_actions",
    }
    assert report["summary"]["failure_attempt_count"] == 5
    assert report["summary"]["open_failure_count"] == 4
    assert report["summary"]["cleared_failure_count"] == 1
    assert [group["target_type"] for group in report["failure_groups"]] == [
        "jira",
        "linear",
        "github",
    ]
    assert report["failure_groups"][0]["open_failure_count"] == 2
    assert report["failure_groups"][0]["retry_priority"] == "p1"
    assert report["failure_groups"][1]["latest_error"] == "rate limited"
    assert {row["idea_id"] for row in report["affected_ideas"]} == {"idea-a", "idea-b", "idea-c"}


def test_publication_failure_triage_clears_latest_success_for_same_target(store: Store) -> None:
    _seed_publications(store)

    report = build_publication_failure_triage(store)

    assert all("idea-cleared" not in group["affected_idea_ids"] for group in report["failure_groups"])
    assert all(row["idea_id"] != "idea-cleared" for row in report["affected_ideas"])


def test_publication_failure_triage_renders_and_validates(store: Store) -> None:
    _seed_publications(store)
    report = build_publication_failure_triage(store)

    assert json.loads(render_publication_failure_triage(report, fmt="json")) == report
    markdown = render_publication_failure_triage(report, fmt="markdown")
    assert markdown.startswith("# Publication Failure Triage")
    assert "## Failure Groups" in markdown
    rows = list(csv.DictReader(StringIO(render_publication_failure_triage(report, fmt="csv"))))
    assert [row["target_type"] for row in rows] == ["jira", "linear", "github"]
    assert rows[0]["open_failure_count"] == "2"

    with pytest.raises(ValueError, match="Unsupported publication failure triage format: yaml"):
        render_publication_failure_triage(report, fmt="yaml")
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_publication_failure_triage(store, limit=0)


def _seed_publications(store: Store) -> None:
    for idea_id in ("idea-a", "idea-b", "idea-c", "idea-cleared"):
        store.insert_buildable_unit(_unit(idea_id))

    _attempt(store, "idea-a", "jira", "https://jira.example/A", "failed", 500, "server exploded", "2026-05-01T00:00:00")
    _attempt(store, "idea-b", "jira", "https://jira.example/A", "failed", 503, "service unavailable", "2026-05-03T00:00:00")
    _attempt(store, "idea-a", "linear", "https://linear.example/A", "failed", 429, "rate limited", "2026-05-04T00:00:00")
    _attempt(store, "idea-c", "github", "https://github.example/C", "failed", 422, "validation failed", "2026-05-02T00:00:00")
    _attempt(store, "idea-cleared", "linear", "https://linear.example/ok", "failed", 500, "old failure", "2026-05-01T00:00:00")
    _attempt(store, "idea-cleared", "linear", "https://linear.example/ok", "published", 201, "", "2026-05-05T00:00:00")


def _attempt(
    store: Store,
    idea_id: str,
    target_type: str,
    target_url: str,
    status: str,
    response_status: int,
    error: str,
    created_at: str,
) -> None:
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type=target_type,
        target_url=target_url,
        status=status,
        response_status=response_status,
        error=error,
    )
    store.conn.execute(
        "UPDATE publication_history SET created_at = ? WHERE id = ?",
        (created_at, attempt["id"]),
    )
    store._commit()


def _unit(idea_id: str) -> BuildableUnit:
    return BuildableUnit(
        id=idea_id,
        title=idea_id,
        one_liner="one",
        category=BuildableCategory.CLI_TOOL,
        problem="problem",
        solution="solution",
        value_proposition="value",
        status="approved",
    )
