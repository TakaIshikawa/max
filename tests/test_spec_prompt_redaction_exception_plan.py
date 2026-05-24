from __future__ import annotations

from max.spec import generate_prompt_redaction_exception_plan


def test_prompt_redaction_exception_plan_normalizes_aliases_and_evidence() -> None:
    plan = generate_prompt_redaction_exception_plan(
        {
            "evidence": {"signal_ids": ["sig-redaction"]},
            "metadata": {
                "prompt_redaction_exception": {
                    "prompts": [{"prompt": "support escalation transcript prompts", "purpose": "incident triage"}],
                    "rationale": ["need raw prompt text for disputed incident triage"],
                    "redaction_controls": ["tenant-limited raw prompt access"],
                    "monitoring": ["daily sensitive token sample"],
                    "access_review": ["privacy reviewer"],
                    "rollback": ["sensitive prompt drift exceeds threshold"],
                }
            },
        }
    )

    assert plan["exempt_prompt_categories"][0]["name"] == "support escalation transcript prompts"
    assert plan["exempt_prompt_categories"][0]["purpose"] == "incident triage"
    assert plan["scope_limits"][0]["name"] == "tenant-limited raw prompt access"
    assert plan["rollback_criteria"][0]["name"] == "sensitive prompt drift exceeds threshold"
    assert set(plan) >= {
        "exempt_prompt_categories",
        "exception_rationale",
        "scope_limits",
        "monitoring",
        "access_review",
        "rollback_criteria",
        "evidence_references",
    }
    assert plan["monitoring"][0]["evidence_reference_ids"] == ["EV1"]
    assert plan["evidence_references"][0]["reference"] == "signal:sig-redaction"


def test_prompt_redaction_exception_plan_defaults_are_actionable() -> None:
    plan = generate_prompt_redaction_exception_plan({})

    assert plan["exempt_prompt_categories"][0]["name"] == "temporary prompt redaction exception"
    assert "default prompt redaction" in plan["exception_rationale"][0]["description"]
    assert "restore default redaction" in plan["rollback_criteria"][0]["name"]


def test_prompt_redaction_exception_plan_accepts_category_alias() -> None:
    plan = generate_prompt_redaction_exception_plan(
        {"metadata": {"prompt_redaction_exception": {"categories": ["regulated support prompts"]}}}
    )

    assert plan["exempt_prompt_categories"][0]["name"] == "regulated support prompts"
