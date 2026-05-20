from __future__ import annotations

import json

from max.analysis.design_brief_vendor_onboarding_readiness_plan import (
    KIND,
    build_design_brief_vendor_onboarding_readiness_plan,
    render_design_brief_vendor_onboarding_readiness_plan,
)


def test_vendor_onboarding_readiness_plan_builds_report_and_sparse_gaps() -> None:
    report = build_design_brief_vendor_onboarding_readiness_plan(
        _Store(_brief(), _idea()), "dbf-vendor-1"
    )
    sparse = build_design_brief_vendor_onboarding_readiness_plan(
        _Store(_brief(sparse=True), _idea(sparse=True)), "dbf-vendor-1"
    )

    assert report is not None
    assert report == build_design_brief_vendor_onboarding_readiness_plan(
        _Store(_brief(), _idea()), "dbf-vendor-1"
    )
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert report["readiness_decision"]["status"] == "ready_for_vendor_review"
    assert report["vendor_requirements"]
    assert report["onboarding_steps"]
    assert report["dependency_checks"]
    assert report["owner_handoffs"]
    assert sparse is not None
    assert [gap["id"] for gap in sparse["evidence_gaps"]] == [
        "missing_vendor_owner",
        "missing_dependency_evidence",
        "missing_onboarding_validation",
    ]
    assert (
        json.loads(render_design_brief_vendor_onboarding_readiness_plan(report, "json")) == report
    )
    assert "## Dependency Checks" in render_design_brief_vendor_onboarding_readiness_plan(report)
    assert (
        build_design_brief_vendor_onboarding_readiness_plan(_Store(_brief(), _idea()), "missing")
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
        "id": "dbf-vendor-1",
        "title": "Vendor Brief",
        "lead_idea_id": "idea-vendor-1",
        "source_idea_ids": ["idea-vendor-1"],
        "sources": [{"idea_id": "idea-vendor-1", "role": "lead", "rank": 0}],
        "merged_product_concept": "Vendor integration workflow",
        "mvp_scope": [] if sparse else ["Vendor API"],
        "validation_plan": "" if sparse else "Validate procurement onboarding.",
        "risks": [] if sparse else ["Integration dependency on vendor API."],
    }


def _idea(*, sparse: bool = False) -> dict:
    return {
        "id": "idea-vendor-1",
        "specific_user": "" if sparse else "ops admins",
        "buyer": "" if sparse else "Procurement VP",
        "workflow_context": "" if sparse else "vendor onboarding",
        "evidence_signals": [] if sparse else ["vendor checklist"],
        "domain_risks": [] if sparse else ["dependency risk"],
        "tech_approach": "" if sparse else "vendor integration",
    }
