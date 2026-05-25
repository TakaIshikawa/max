from __future__ import annotations

import json

from max.spec.prompt_template_deprecation_plan import generate_prompt_template_deprecation_plan


def test_prompt_template_deprecation_plan_covers_replacement_rollout_and_gates() -> None:
    plan = generate_prompt_template_deprecation_plan(
        _spec(
            {
                "deprecated_templates": [
                    {
                        "template": "synthesis-v1",
                        "template_id": "tmpl-1",
                        "replacement": "synthesis-v2",
                    }
                ],
                "replacement_mapping": [
                    {"template": "synthesis-v1", "replacement_template": "synthesis-v2"}
                ],
                "compatibility_checks": ["output schema unchanged"],
                "rollout_phases": [{"phase": "canary", "traffic": "10%"}],
                "rollback_criteria": ["quality regression above threshold"],
                "evaluation_gates": [{"metric": "win rate", "threshold": ">= baseline"}],
                "audit_evidence": ["approval record"],
            }
        )
    )

    assert plan["schema_version"] == "max.spec.prompt_template_deprecation_plan.v1"
    assert plan["deprecated_templates"][0]["template"] == "synthesis-v1"
    assert plan["replacement_mapping"][0]["replacement_template"] == "synthesis-v2"
    assert plan["compatibility_checks"][0]["name"] == "output schema unchanged"
    assert plan["rollout_phases"][0]["traffic"] == "10%"
    assert plan["rollback_criteria"][0]["name"] == "quality regression above threshold"
    assert plan["evaluation_gates"][0]["metric"] == "win rate"
    assert plan["audit_evidence"][0]["name"] == "approval record"
    assert plan["blockers"] == []
    assert json.loads(json.dumps(plan)) == plan


def test_prompt_template_deprecation_plan_flags_templates_without_replacements() -> None:
    plan = generate_prompt_template_deprecation_plan(
        _spec({"templates": [{"template": "ideation-v1", "template_id": "tmpl-old"}]})
    )

    assert plan["deprecated_templates"][0]["name"] == "ideation-v1"
    assert plan["replacement_mapping"] == []
    assert plan["blockers"][0]["name"] == "missing replacement for ideation-v1"
    assert plan["blockers"][0]["template_id"] == "tmpl-old"
    assert "quality comparison" in plan["evaluation_gates"][0]["name"]
    assert set(plan) >= {
        "replacement_mapping",
        "compatibility_checks",
        "rollout_phases",
        "rollback_criteria",
        "evaluation_gates",
        "audit_evidence",
    }


def _spec(hints: dict) -> dict:
    return {
        "metadata": {"prompt_template_deprecation": hints},
        "evidence": {"signal_ids": ["pt-1"]},
    }
