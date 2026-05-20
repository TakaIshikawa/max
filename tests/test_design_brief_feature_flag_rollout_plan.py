from __future__ import annotations

import json

from max.analysis import generate_design_brief_feature_flag_rollout_plan as exported_generate
from max.analysis.design_brief_feature_flag_rollout_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_feature_flag_rollout_plan,
)


def test_feature_flag_rollout_plan_groups_stages_by_sorted_flag() -> None:
    brief = {
        "metadata": {
            "feature_flag_rollout_plan": {
                "flags": [
                    {"flag": "zeta search", "owner": "eng", "kill_switch": "disable flag", "guardrail_metrics": ["error rate"], "evidence": ["launch doc"]},
                    {"flag": "alpha editor", "owner": "pm", "kill_switch": "config off", "guardrail_metrics": ["latency"], "evidence": ["metrics"]},
                ],
                "stages": [{"stage": "beta", "percent": 20}, {"stage": "internal", "percent": 5}],
            }
        }
    }

    plan = generate_design_brief_feature_flag_rollout_plan(brief)

    assert plan == generate_design_brief_feature_flag_rollout_plan(brief)
    assert json.loads(json.dumps(plan)) == plan
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [row["flag"] for row in plan["feature_flags"]] == ["alpha editor", "zeta search"]
    assert [row["flag"] for row in plan["rollout_stages"][:2]] == ["alpha editor", "alpha editor"]
    assert plan["summary"]["recommendation_status"] == "ready"
    assert exported_generate({})["kind"] == KIND


def test_feature_flag_rollout_plan_reports_missing_kill_switch_and_metrics() -> None:
    plan = generate_design_brief_feature_flag_rollout_plan(
        {"feature_flag_rollout_plan": {"flags": [{"name": "beta mode"}]}}
    )

    assert plan["summary"]["recommendation_status"] == "blocked"
    assert [risk["id"] for risk in plan["launch_risks"]] == [
        "beta_mode_missing_kill_switch",
        "beta_mode_missing_guardrail_metrics",
        "beta_mode_missing_owner",
    ]
