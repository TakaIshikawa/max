from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_release_train_readiness_plan import (
    KIND,
    build_design_brief_release_train_readiness_plan,
    release_train_readiness_plan_filename,
    render_design_brief_release_train_readiness_plan,
)


def test_release_train_readiness_plan_builds_complete_deterministic_report() -> None:
    report = build_design_brief_release_train_readiness_plan(_brief())

    assert report == build_design_brief_release_train_readiness_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert report["release_train"] == {
        "id": "RT1",
        "name": "Orion 2026.06",
        "target_date": "2026-06-15",
        "description": "Release train readiness review.",
    }
    assert [row["description"] for row in report["release_scope"]] == [
        "Admin launch",
        "Billing migration",
    ]
    assert [row["name"] for row in report["readiness_gates"]] == [
        "API contract ready",
        "Billing dependency passed",
    ]
    assert [row["owner"] for row in report["owner_coverage"]] == [
        "Product lead",
        "Engineering lead",
    ]
    assert report["rollback_evidence"][0]["status"] == "ready"
    assert report["recommendation"]["status"] == "ready_for_go_no_go_review"
    assert report["missing_input_warnings"] == []


def test_release_train_readiness_plan_sparse_brief_returns_conservative_warnings() -> None:
    report = build_design_brief_release_train_readiness_plan({"id": "dbf-release-sparse"})

    assert report["summary"]["recommendation_status"] == "blocked_pending_release_inputs"
    assert [warning["id"] for warning in report["missing_input_warnings"]] == [
        "missing_train_name",
        "missing_train_date",
        "missing_release_scope",
        "missing_dependency_gates",
        "missing_go_no_go_owners",
        "missing_rollback_rehearsal",
    ]
    assert json.loads(json.dumps(report)) == report


def test_release_train_readiness_plan_renderers_and_filename() -> None:
    report = build_design_brief_release_train_readiness_plan(_brief())

    assert json.loads(render_design_brief_release_train_readiness_plan(report, "json")) == report
    markdown = render_design_brief_release_train_readiness_plan(report, "markdown")
    assert markdown.startswith("# Release Train Readiness Plan: Release Train Brief")
    assert "## Readiness Gates" in markdown
    assert (
        release_train_readiness_plan_filename(_brief())
        == "dbf-release-1-Release-Train-Brief-release-train-readiness-plan.md"
    )
    assert release_train_readiness_plan_filename(_brief(), "json").endswith(".json")
    with pytest.raises(ValueError, match="Unsupported release train readiness plan format"):
        render_design_brief_release_train_readiness_plan(report, "yaml")


def _brief() -> dict:
    return {
        "id": "dbf-release-1",
        "title": "Release Train Brief",
        "source_idea_ids": ["idea-release-1"],
        "release_train_name": "Orion 2026.06",
        "release_train_date": "2026-06-15",
        "release_scope": ["Admin launch", "Billing migration", "Admin launch"],
        "dependency_gates": ["API contract ready", "Billing dependency passed"],
        "go_no_go_owners": ["Product lead", "Engineering lead", "Product lead"],
        "rollback_rehearsal_status": ["Rollback rehearsal ready"],
    }
