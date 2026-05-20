from __future__ import annotations

import json

from max.analysis.design_brief_customer_advisory_board_plan import (
    KIND,
    build_design_brief_customer_advisory_board_plan,
    render_design_brief_customer_advisory_board_plan,
)


def test_customer_advisory_board_plan_builds_report_and_sparse_gaps() -> None:
    report = build_design_brief_customer_advisory_board_plan(_Store(_brief(), _idea()), "dbf-cab-1")
    sparse = build_design_brief_customer_advisory_board_plan(
        _Store(_brief(sparse=True), _idea(sparse=True)), "dbf-cab-1"
    )

    assert report is not None
    assert report == build_design_brief_customer_advisory_board_plan(
        _Store(_brief(), _idea()), "dbf-cab-1"
    )
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert report["participant_segments"][0]["name"] == "enterprise admins"
    assert report["feedback_themes"]
    assert report["session_agenda"]
    assert report["follow_up_decisions"]
    assert sparse is not None
    assert [gap["id"] for gap in sparse["evidence_gaps"]] == [
        "missing_target_user",
        "missing_customer_evidence",
        "missing_validation_agenda",
    ]
    assert json.loads(render_design_brief_customer_advisory_board_plan(report, "json")) == report
    assert "## Participant Segments" in render_design_brief_customer_advisory_board_plan(report)
    assert (
        build_design_brief_customer_advisory_board_plan(_Store(_brief(), _idea()), "missing")
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
        "id": "dbf-cab-1",
        "title": "CAB Brief",
        "lead_idea_id": "idea-cab-1",
        "source_idea_ids": ["idea-cab-1"],
        "sources": [{"idea_id": "idea-cab-1", "role": "lead", "rank": 0}],
        "merged_product_concept": "Admin workflow",
        "mvp_scope": [] if sparse else ["Feedback review"],
        "validation_plan": "" if sparse else "Run CAB validation agenda.",
        "risks": [],
    }


def _idea(*, sparse: bool = False) -> dict:
    return {
        "id": "idea-cab-1",
        "specific_user": "" if sparse else "enterprise admins",
        "buyer": "" if sparse else "Customer VP",
        "workflow_context": "" if sparse else "admin onboarding",
        "evidence_signals": [] if sparse else ["customer interview"],
        "inspiring_insights": [] if sparse else ["CAB request"],
    }
