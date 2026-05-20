from __future__ import annotations

import json

from max.analysis.design_brief_experiment_rollout_readiness_plan import (
    KIND,
    build_design_brief_experiment_rollout_readiness_plan,
    render_design_brief_experiment_rollout_readiness_plan,
)


def test_experiment_rollout_readiness_plan_builds_report_and_sparse_gaps() -> None:
    report = build_design_brief_experiment_rollout_readiness_plan(
        _Store(_brief(), _idea()), "dbf-exp-1"
    )
    sparse = build_design_brief_experiment_rollout_readiness_plan(
        _Store(_brief(sparse=True), _idea(sparse=True)), "dbf-exp-1"
    )

    assert report is not None
    assert report == build_design_brief_experiment_rollout_readiness_plan(
        _Store(_brief(), _idea()), "dbf-exp-1"
    )
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert report["rollout_decision"]["status"] == "ready_for_limited_rollout"
    assert report["rollout_hypotheses"]
    assert report["cohort_plan"]
    assert report["guardrail_checks"]
    assert report["telemetry_requirements"]
    assert sparse is not None
    assert [gap["id"] for gap in sparse["evidence_gaps"]] == [
        "missing_cohort",
        "missing_telemetry",
        "missing_guardrail",
    ]
    assert (
        json.loads(render_design_brief_experiment_rollout_readiness_plan(report, "json")) == report
    )
    assert "## Telemetry Requirements" in render_design_brief_experiment_rollout_readiness_plan(
        report
    )
    assert (
        build_design_brief_experiment_rollout_readiness_plan(_Store(_brief(), _idea()), "missing")
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
        "id": "dbf-exp-1",
        "title": "Experiment Brief",
        "lead_idea_id": "idea-exp-1",
        "source_idea_ids": ["idea-exp-1"],
        "sources": [{"idea_id": "idea-exp-1", "role": "lead", "rank": 0}],
        "merged_product_concept": "Experiment workflow",
        "mvp_scope": [] if sparse else ["Limited cohort"],
        "validation_plan": "" if sparse else "Run validation with telemetry dashboard.",
        "risks": [] if sparse else ["Failure guardrail for rollout."],
    }


def _idea(*, sparse: bool = False) -> dict:
    return {
        "id": "idea-exp-1",
        "specific_user": "" if sparse else "beta admins",
        "buyer": "" if sparse else "Growth VP",
        "workflow_context": "" if sparse else "feature trial",
        "evidence_signals": [] if sparse else ["telemetry metric"],
        "domain_risks": [] if sparse else ["rollout risk"],
    }
