from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_training_content_gap_plan import (
    KIND,
    build_design_brief_training_content_gap_plan,
    render_design_brief_training_content_gap_plan,
    training_content_gap_plan_filename,
)


def test_training_content_gap_plan_builds_role_based_rows() -> None:
    report = build_design_brief_training_content_gap_plan(_brief())

    assert report == build_design_brief_training_content_gap_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert [row["id"] for row in report["training_gap_rows"]] == ["A2", "A3", "A1"]
    assert report["training_gap_rows"][0] == {
        "id": "A2",
        "role": "Support",
        "asset": "Escalation lab",
        "asset_type": "exercise",
        "coverage_status": "missing",
        "criticality": "critical",
        "owner": "Support enablement",
        "due_window": "overdue",
        "launch_blocker": True,
        "evidence_refs": [],
        "action": "Close exercise coverage gap for Support.",
    }
    assert report["summary"]["missing_critical_asset_count"] == 1
    assert report["summary"]["unowned_content_count"] == 0
    assert report["summary"]["overdue_blocker_count"] == 1
    assert report["summary"]["coverage_by_role"]["Sales"]["covered"] == 1


def test_training_content_gap_plan_sparse_input_defaults_and_blocks() -> None:
    report = build_design_brief_training_content_gap_plan({"id": "dbf-training-sparse"})

    row = report["training_gap_rows"][0]
    assert row["role"] == "Target role 1"
    assert row["asset_type"] == "training module"
    assert row["coverage_status"] == "missing"
    assert row["owner"] == "Training owner"
    assert row["launch_blocker"] is False
    assert report["summary"]["unowned_content_count"] == 1
    assert report["summary"]["readiness_status"] == "ready_for_training_launch"


def test_training_content_gap_plan_blocker_prioritization_is_stable() -> None:
    report = build_design_brief_training_content_gap_plan(
        {
            "id": "dbf-training-order",
            "required_training_assets": [
                {"id": "covered", "role": "Admin", "asset_type": "guide", "status": "covered"},
                {"id": "block-b", "role": "Support", "asset_type": "lab", "criticality": "critical"},
                {"id": "block-a", "role": "Sales", "asset_type": "demo", "criticality": "critical"},
            ],
        }
    )

    assert [row["id"] for row in report["training_gap_rows"]] == ["block-a", "block-b", "covered"]
    assert [row["id"] for row in report["blocker_priorities"]] == ["block-a", "block-b"]


def test_training_content_gap_plan_renderers_and_filename() -> None:
    report = build_design_brief_training_content_gap_plan(_brief())

    assert json.loads(render_design_brief_training_content_gap_plan(report, "json")) == report
    markdown = render_design_brief_training_content_gap_plan(report, "markdown")
    assert markdown.startswith("# Training Content Gap Plan: Training Gap Brief")
    assert "## Readiness Summary" in markdown
    assert "## Training Gaps" in markdown
    assert "## Launch Blockers" in markdown
    assert "## Unowned Content" in markdown
    assert (
        training_content_gap_plan_filename(_brief())
        == "dbf-training-1-Training-Gap-Brief-training-content-gap-plan.md"
    )
    assert training_content_gap_plan_filename(_brief(), "json").endswith(".json")
    with pytest.raises(ValueError, match="Unsupported training content gap plan format"):
        render_design_brief_training_content_gap_plan(report, "yaml")


def _brief() -> dict:
    return {
        "id": "dbf-training-1",
        "title": "Training Gap Brief",
        "source_idea_ids": ["idea-training-1"],
        "required_training_assets": [
            {
                "id": "A1",
                "role": "Sales",
                "asset": "Demo script",
                "asset_type": "script",
                "coverage_status": "covered",
                "owner": "Sales enablement",
                "evidence_refs": ["doc-demo", "doc-demo"],
            },
            {
                "id": "A2",
                "role": "Support",
                "asset": "Escalation lab",
                "asset_type": "exercise",
                "coverage_status": "missing",
                "criticality": "critical",
                "owner": "Support enablement",
                "due_window": "overdue",
            },
            {
                "id": "A3",
                "role": "Admin",
                "asset": "Configuration guide",
                "asset_type": "guide",
                "coverage_status": "partial",
                "owner": "Product education",
                "due_window": "launch minus 2 weeks",
                "evidence_refs": ["draft-guide"],
            },
        ],
    }
