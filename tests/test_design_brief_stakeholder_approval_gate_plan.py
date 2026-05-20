from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_stakeholder_approval_gate_plan import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_stakeholder_approval_gate_plan,
    render_design_brief_stakeholder_approval_gate_plan,
    stakeholder_approval_gate_plan_filename,
)


def test_stakeholder_approval_gate_plan_builds_deterministic_report() -> None:
    store = _Store(_brief(), _idea())

    report = build_design_brief_stakeholder_approval_gate_plan(store, "dbf-approval-1")
    repeated = build_design_brief_stakeholder_approval_gate_plan(store, "dbf-approval-1")

    assert report is not None
    assert report == repeated
    assert json.loads(json.dumps(report)) == report
    assert list(report) == [
        "schema_version",
        "kind",
        "source",
        "design_brief",
        "summary",
        "approval_gates",
        "stakeholder_decisions",
        "blocker_register",
        "evidence_references",
        "evidence_gaps",
        "open_questions",
        "source_ideas",
    ]
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["primary_approver"] == "Revenue VP"
    assert report["approval_gates"][0]["owner"] == "Revenue VP"
    assert report["blocker_register"][0]["severity"] == "high"


def test_stakeholder_approval_gate_sparse_and_renderers() -> None:
    store = _Store(_brief(sparse=True), _idea(sparse=True))

    report = build_design_brief_stakeholder_approval_gate_plan(store, "dbf-approval-1")

    assert report is not None
    assert build_design_brief_stakeholder_approval_gate_plan(store, "missing") is None
    assert [gap["id"] for gap in report["evidence_gaps"]] == [
        "missing_buyer_or_stakeholder",
        "missing_blocker_evidence",
        "missing_blocker_register",
    ]
    assert json.loads(render_design_brief_stakeholder_approval_gate_plan(report, "json")) == report
    markdown = render_design_brief_stakeholder_approval_gate_plan(report, "markdown")
    assert markdown.startswith("# Stakeholder Approval Gate Plan: Approval Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Approval Gates" in markdown
    assert (
        stakeholder_approval_gate_plan_filename(report["design_brief"])
        == "dbf-approval-1-Approval-Brief-stakeholder-approval-gate-plan.md"
    )
    assert stakeholder_approval_gate_plan_filename(report["design_brief"], "json").endswith(".json")
    with pytest.raises(ValueError, match="Unsupported stakeholder approval gate plan format"):
        render_design_brief_stakeholder_approval_gate_plan(report, "yaml")


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
        "id": "dbf-approval-1",
        "title": "Approval Brief",
        "domain": "revenue",
        "theme": "approvals",
        "readiness_score": 74.0,
        "design_status": "approved",
        "lead_idea_id": "idea-approval-1",
        "source_idea_ids": ["idea-approval-1"],
        "sources": [{"idea_id": "idea-approval-1", "role": "lead", "rank": 0}],
        "merged_product_concept": "Approval workflow",
        "mvp_scope": [] if sparse else ["Approver dashboard"],
        "validation_plan": "" if sparse else "Decision criteria validated with sponsor.",
        "risks": [] if sparse else ["Security blocker needs approval evidence."],
    }


def _idea(*, sparse: bool = False) -> dict:
    return {
        "id": "idea-approval-1",
        "specific_user": "" if sparse else "sales leaders",
        "buyer": "" if sparse else "Revenue VP",
        "workflow_context": "" if sparse else "discount approval",
        "solution": "Approval workflow",
        "evidence_signals": [] if sparse else ["sponsor notes"],
        "domain_risks": [] if sparse else ["Security blocker needs approval evidence."],
    }
