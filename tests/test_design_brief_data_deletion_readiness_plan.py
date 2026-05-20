from __future__ import annotations

import json

from max.analysis.design_brief_data_deletion_readiness_plan import (
    KIND,
    build_design_brief_data_deletion_readiness_plan,
    render_design_brief_data_deletion_readiness_plan,
)


def test_data_deletion_readiness_plan_builds_report_and_sparse_gaps() -> None:
    report = build_design_brief_data_deletion_readiness_plan(
        _Store(_brief(), _idea()), "dbf-delete-1"
    )
    sparse = build_design_brief_data_deletion_readiness_plan(
        _Store(_brief(sparse=True), _idea(sparse=True)), "dbf-delete-1"
    )

    assert report is not None
    assert report == build_design_brief_data_deletion_readiness_plan(
        _Store(_brief(), _idea()), "dbf-delete-1"
    )
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert report["readiness_decision"]["status"] == "privacy_review_required"
    assert report["deletion_triggers"]
    assert report["data_categories"]
    assert report["verification_checks"]
    assert report["owner_handoffs"]
    assert sparse is not None
    assert [gap["id"] for gap in sparse["evidence_gaps"]] == [
        "missing_data_category",
        "missing_deletion_owner",
        "missing_verification_evidence",
    ]
    assert json.loads(render_design_brief_data_deletion_readiness_plan(report, "json")) == report
    assert "## Data Categories" in render_design_brief_data_deletion_readiness_plan(report)
    assert (
        build_design_brief_data_deletion_readiness_plan(_Store(_brief(), _idea()), "missing")
        is None
    )


class _Store:
    def __init__(self, brief: dict, idea: dict) -> None:
        self.brief = brief
        self.idea = idea

    def get_design_brief(self, brief_id: str) -> dict | None:
        return self.brief if brief_id == self.brief["id"] else None

    def get_buildable_unit(self, idea_id: str) -> dict | None:
        return self.idea if idea_id == self.idea["id"] else None


def _brief(*, sparse: bool = False) -> dict:
    return {
        "id": "dbf-delete-1",
        "title": "Deletion Brief",
        "lead_idea_id": "idea-delete-1",
        "source_idea_ids": ["idea-delete-1"],
        "sources": [{"idea_id": "idea-delete-1", "role": "lead", "rank": 0}],
        "merged_product_concept": "Privacy deletion workflow",
        "mvp_scope": [] if sparse else ["Account deletion"],
        "validation_plan": "" if sparse else "Verify deletion audit logs.",
        "risks": [] if sparse else ["Privacy retention deletion compliance risk."],
    }


def _idea(*, sparse: bool = False) -> dict:
    return {
        "id": "idea-delete-1",
        "specific_user": "" if sparse else "privacy admins",
        "buyer": "" if sparse else "Privacy Officer",
        "workflow_context": "" if sparse else "data deletion requests",
        "evidence_signals": [] if sparse else ["deletion export"],
        "domain_risks": [] if sparse else ["residency compliance"],
    }
