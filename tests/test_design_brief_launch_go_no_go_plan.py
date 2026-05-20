from __future__ import annotations

import json

from max.analysis.design_brief_launch_go_no_go_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_launch_go_no_go_plan,
)


def test_launch_go_no_go_plan_sorts_sections_and_go_decision() -> None:
    plan = generate_design_brief_launch_go_no_go_plan(
        {
            "metadata": {
                "launch_go_no_go_plan": {
                    "criteria": [
                        {"name": "Support ready", "owner": "Support", "status": "met"},
                        {"name": "Billing ready", "owner": "Finance", "status": "approved"},
                    ],
                    "approvers": [{"name": "GM", "decision": "approved"}],
                    "blockers": [{"name": "Docs typo", "severity": "low", "status": "closed"}],
                    "rollback_triggers": [{"name": "error budget breach", "owner": "SRE"}],
                    "evidence": ["EV1"],
                }
            }
        }
    )

    assert plan["kind"] == KIND
    assert plan["schema_version"] == SCHEMA_VERSION
    assert [row["name"] for row in plan["launch_criteria"]] == ["Billing ready", "Support ready"]
    assert [row["name"] for row in plan["gate_approvers"]] == ["GM"]
    assert [row["name"] for row in plan["rollback_triggers"]] == ["error budget breach"]
    assert plan["summary"]["launch_decision"] == "go"
    assert json.loads(json.dumps(plan)) == plan


def test_launch_go_no_go_plan_blocks_on_high_unresolved_criteria() -> None:
    plan = generate_design_brief_launch_go_no_go_plan(
        {"launch_go_no_go_plan": {"criteria": [{"name": "Privacy signoff", "severity": "high", "status": "pending"}]}}
    )

    assert plan["summary"]["launch_decision"] == "no_go"
    assert plan["blockers"][0]["name"] == "Unresolved Privacy signoff"
    assert json.loads(json.dumps(plan)) == plan
