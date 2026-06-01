from __future__ import annotations

from max.spec import generate_llm_provider_terms_change_review_plan


def test_llm_provider_terms_change_review_plan_escalates_near_term_changes() -> None:
    plan = generate_llm_provider_terms_change_review_plan(
        {
            "metadata": {
                "llm_provider_terms_change": {
                    "provider": "ModelCo",
                    "effective_date": "2026-06-10",
                    "changed_terms": ["training opt-out", "retention window"],
                    "affected_products": ["support copilot", "summary API"],
                    "data_use_impacts": ["customer prompts may be retained for abuse monitoring"],
                    "owner": "ml_platform_owner",
                    "legal_reviewer": "legal_owner",
                    "mitigation_actions": [
                        "disable provider logging",
                        "disable provider logging",
                        "route sensitive prompts to approved fallback",
                    ],
                }
            },
            "evidence": {"signal_ids": ["sig-terms"]},
        },
        as_of="2026-06-01",
    )

    assert plan["schema_version"] == "max.spec.llm_provider_terms_change_review_plan.v1"
    assert plan["kind"] == "max.spec.llm_provider_terms_change_review_plan"
    assert plan["summary"]["provider"] == "ModelCo"
    assert plan["summary"]["review_urgency"] == "near_term"
    assert plan["summary"]["days_until_effective"] == 9
    assert plan["impact_review"][0]["name"] == "summary API"
    assert plan["legal_assessment"][0]["name"] == "retention window"
    assert plan["communication"][1]["owner"] == "legal_owner"
    assert plan["approval_gates"][1]["name"] == "legal approval"
    assert plan["escalation_tasks"][0]["status"] == "required"
    assert plan["escalation_tasks"][0]["severity"] == "critical"
    assert [item["name"] for item in plan["mitigation"]].count("disable provider logging") == 1


def test_llm_provider_terms_change_review_plan_validates_required_fields() -> None:
    plan = generate_llm_provider_terms_change_review_plan({}, as_of="2026-06-01")

    assert plan["summary"]["validation_issue_count"] == 6
    assert plan["validation_issues"] == [
        "missing_provider",
        "missing_effective_date",
        "missing_changed_terms",
        "missing_affected_products",
        "missing_owner",
        "missing_legal_reviewer",
    ]
    assert plan["summary"]["review_urgency"] == "standard"
    assert plan["escalation_tasks"] == []
    assert plan["impact_review"][0]["name"] == "affected LLM product"
