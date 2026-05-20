from __future__ import annotations

import json

from max.analysis.design_brief_revenue_at_risk_plan import (
    KIND,
    build_design_brief_revenue_at_risk_plan,
    render_design_brief_revenue_at_risk_plan,
)


def test_revenue_at_risk_plan_builds_report_and_sparse_gaps() -> None:
    report = build_design_brief_revenue_at_risk_plan(_Store(_brief(), _idea()), "dbf-revenue-1")
    sparse = build_design_brief_revenue_at_risk_plan(
        _Store(_brief(sparse=True), _idea(sparse=True)), "dbf-revenue-1"
    )

    assert report is not None
    assert report == build_design_brief_revenue_at_risk_plan(
        _Store(_brief(), _idea()), "dbf-revenue-1"
    )
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert report["revenue_posture"]["status"] == "revenue_at_risk"
    assert report["risk_drivers"]
    assert report["affected_segments"]
    assert report["mitigation_actions"]
    assert report["owner_assignments"]
    assert sparse is not None
    assert [gap["id"] for gap in sparse["evidence_gaps"]] == [
        "missing_buyer",
        "missing_customer_segment",
        "missing_mitigation_evidence",
    ]
    assert json.loads(render_design_brief_revenue_at_risk_plan(report, "json")) == report
    assert "## Mitigation Actions" in render_design_brief_revenue_at_risk_plan(report)
    assert build_design_brief_revenue_at_risk_plan(_Store(_brief(), _idea()), "missing") is None


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
        "id": "dbf-revenue-1",
        "title": "Revenue Brief",
        "lead_idea_id": "idea-revenue-1",
        "source_idea_ids": ["idea-revenue-1"],
        "sources": [{"idea_id": "idea-revenue-1", "role": "lead", "rank": 0}],
        "merged_product_concept": "Renewal risk workflow",
        "mvp_scope": [] if sparse else ["Renewal dashboard"],
        "validation_plan": "" if sparse else "Validate mitigation with account team.",
        "risks": [] if sparse else ["Churn and renewal pricing risk for customer-impact accounts."],
    }


def _idea(*, sparse: bool = False) -> dict:
    return {
        "id": "idea-revenue-1",
        "specific_user": "" if sparse else "account managers",
        "buyer": "" if sparse else "Revenue VP",
        "workflow_context": "" if sparse else "renewal workflow",
        "evidence_signals": [] if sparse else ["renewal notes"],
        "domain_risks": [] if sparse else ["expansion risk"],
    }
