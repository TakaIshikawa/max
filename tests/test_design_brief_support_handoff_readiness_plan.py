from __future__ import annotations

import json

from max.analysis.design_brief_support_handoff_readiness_plan import (
    KIND,
    build_design_brief_support_handoff_readiness_plan,
    render_design_brief_support_handoff_readiness_plan,
)


def test_support_handoff_readiness_plan_builds_report_and_sparse_gaps() -> None:
    report = build_design_brief_support_handoff_readiness_plan(
        _Store(_brief(), _idea()), "dbf-support-1"
    )
    sparse = build_design_brief_support_handoff_readiness_plan(
        _Store(_brief(sparse=True), _idea(sparse=True)), "dbf-support-1"
    )

    assert report is not None
    assert report == build_design_brief_support_handoff_readiness_plan(
        _Store(_brief(), _idea()), "dbf-support-1"
    )
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert report["readiness_summary"]["status"] == "ready"
    assert report["support_artifacts"]
    assert report["training_needs"]
    assert report["known_issue_intake"]
    assert report["ownership_handoffs"]
    assert sparse is not None
    assert [gap["id"] for gap in sparse["evidence_gaps"]] == [
        "missing_support_owner",
        "missing_artifact_evidence",
        "missing_training_validation",
    ]
    assert json.loads(render_design_brief_support_handoff_readiness_plan(report, "json")) == report
    assert "## Training Needs" in render_design_brief_support_handoff_readiness_plan(report)
    assert (
        build_design_brief_support_handoff_readiness_plan(_Store(_brief(), _idea()), "missing")
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
        "id": "dbf-support-1",
        "title": "Support Brief",
        "lead_idea_id": "idea-support-1",
        "source_idea_ids": ["idea-support-1"],
        "sources": [{"idea_id": "idea-support-1", "role": "lead", "rank": 0}],
        "merged_product_concept": "Support workflow",
        "mvp_scope": [] if sparse else ["Support artifact"],
        "validation_plan": "" if sparse else "Validate support training.",
        "risks": [] if sparse else ["Customer workflow issue requires support handoff."],
    }


def _idea(*, sparse: bool = False) -> dict:
    return {
        "id": "idea-support-1",
        "specific_user": "" if sparse else "support agents",
        "buyer": "" if sparse else "Support VP",
        "workflow_context": "" if sparse else "customer support workflow",
        "evidence_signals": [] if sparse else ["support training notes"],
        "domain_risks": [] if sparse else ["known support issue"],
    }
