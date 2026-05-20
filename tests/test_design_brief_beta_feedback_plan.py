from __future__ import annotations

import json

from max.analysis import generate_design_brief_beta_feedback_plan as exported_generate
from max.analysis.design_brief_beta_feedback_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_beta_feedback_plan,
)


def test_beta_feedback_plan_normalizes_complete_input_and_preserves_theme_evidence() -> None:
    brief = {
        "metadata": {
            "beta_feedback_plan": {
                "cohorts": [{"name": "Design partners", "size": 12, "owner": "pm", "evidence": ["crm"]}],
                "channels": [{"channel": "Slack", "sla": "1 business day", "owner": "support", "evidence": ["workspace"]}],
                "owner_assignments": ["pm", "support"],
                "themes": [
                    {"theme": "Workflow gaps", "severity": "high", "evidence": ["call 2", "call 1"]},
                    {"theme": "API friction", "severity": "medium", "evidence": ["ticket 7"]},
                ],
            }
        }
    }

    plan = generate_design_brief_beta_feedback_plan(brief)

    assert plan == generate_design_brief_beta_feedback_plan(brief)
    assert json.loads(json.dumps(plan)) == plan
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["readiness_status"] == "needs_attention"
    assert [theme["theme"] for theme in plan["unresolved_themes"]] == ["API friction", "Workflow gaps"]
    assert plan["unresolved_themes"][1]["evidence_references"] == ["call 1", "call 2"]
    assert exported_generate({})["kind"] == KIND


def test_beta_feedback_plan_reports_missing_cohorts_channels_and_owners() -> None:
    plan = generate_design_brief_beta_feedback_plan({"metadata": {"beta_feedback_plan": {}}})

    assert plan["summary"]["readiness_status"] == "blocked"
    assert [gap["id"] for gap in plan["readiness_gaps"]] == [
        "missing_beta_cohorts",
        "missing_feedback_channels",
        "missing_owner_assignments",
    ]
