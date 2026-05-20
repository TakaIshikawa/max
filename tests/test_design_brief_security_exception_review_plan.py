from __future__ import annotations

import json

from max.analysis.design_brief_security_exception_review_plan import (
    KIND,
    build_design_brief_security_exception_review_plan,
    render_design_brief_security_exception_review_plan,
)


def test_security_exception_review_plan_builds_report_and_sparse_gaps() -> None:
    report = build_design_brief_security_exception_review_plan(
        _Store(_brief(), _idea()), "dbf-sec-1"
    )
    sparse = build_design_brief_security_exception_review_plan(
        _Store(_brief(sparse=True), _idea(sparse=True)), "dbf-sec-1"
    )

    assert report is not None
    assert report == build_design_brief_security_exception_review_plan(
        _Store(_brief(), _idea()), "dbf-sec-1"
    )
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert report["summary"]["high_risk_exception_count"] >= 1
    assert report["exception_candidates"][0]["severity"] == "high"
    assert report["compensating_controls"]
    assert report["approval_requirements"]
    assert report["review_cadence"]
    assert sparse is not None
    assert [gap["id"] for gap in sparse["evidence_gaps"]] == [
        "missing_security_owner",
        "missing_control_evidence",
        "missing_review_cadence",
    ]
    assert json.loads(render_design_brief_security_exception_review_plan(report, "json")) == report
    assert "## Exception Candidates" in render_design_brief_security_exception_review_plan(report)
    assert (
        build_design_brief_security_exception_review_plan(_Store(_brief(), _idea()), "missing")
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
        "id": "dbf-sec-1",
        "title": "Security Brief",
        "lead_idea_id": "idea-sec-1",
        "source_idea_ids": ["idea-sec-1"],
        "sources": [{"idea_id": "idea-sec-1", "role": "lead", "rank": 0}],
        "merged_product_concept": "Security exception workflow",
        "mvp_scope": [] if sparse else ["Exception approval"],
        "validation_plan": "" if sparse else "Review exception expiry cadence.",
        "risks": [] if sparse else ["Security privacy data exception requires review."],
    }


def _idea(*, sparse: bool = False) -> dict:
    return {
        "id": "idea-sec-1",
        "specific_user": "" if sparse else "security admins",
        "buyer": "" if sparse else "CISO",
        "workflow_context": "" if sparse else "exception review",
        "evidence_signals": [] if sparse else ["control review"],
        "domain_risks": [] if sparse else ["access exception"],
    }
