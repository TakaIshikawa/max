from __future__ import annotations

from max.spec.third_party_llm_subprocessor_review_plan import (
    generate_third_party_llm_subprocessor_review_plan,
)


def test_third_party_llm_subprocessor_review_plan_covers_subprocessors_and_controls() -> None:
    plan = generate_third_party_llm_subprocessor_review_plan(
        {
            "subprocessors": [
                {
                    "subprocessor": "ModelCo",
                    "purpose": "support triage completions",
                    "data_access": "redacted support prompts",
                    "region": "us-east-1",
                    "contractual_controls": "DPA and no-training addendum",
                },
                {
                    "subprocessor": "FallbackAI",
                    "purpose": "overflow summarization",
                    "data_access": "case metadata",
                    "region": "eu-central-1",
                    "contractual_controls": "missing",
                },
            ],
            "data_categories": ["support prompts", "case metadata"],
            "regions": ["US processing", "EU failover"],
            "contractual_controls": ["DPA review"],
            "security_questionnaire": ["SOC 2 questionnaire"],
            "customer_notice": ["trust center notice"],
            "fallback_provider": ["approved internal model"],
            "approvals": ["legal, privacy, and security approval"],
        }
    )

    assert plan["title"] == "Third Party LLM Subprocessor Review Plan"
    assert [item["name"] for item in plan["subprocessors"]] == ["FallbackAI", "ModelCo"]
    assert plan["subprocessors"][0]["purpose"] == "overflow summarization"
    assert plan["subprocessors"][0]["data_access"] == "case metadata"
    assert plan["subprocessors"][0]["region"] == "eu-central-1"
    assert plan["contractual_controls"][0]["name"] == "DPA review"
    assert plan["security_review"][0]["name"] == "SOC 2 questionnaire"
    assert plan["customer_notification"][0]["name"] == "trust center notice"
    assert plan["fallback_provider"][0]["name"] == "approved internal model"
    assert plan["approval_checklist"][0]["name"] == "legal, privacy, and security approval"
    assert plan["contractual_risks"][0]["subprocessor"] == "FallbackAI"
    assert plan["contractual_risks"][0]["status"] == "missing_contractual_controls"


def test_third_party_llm_subprocessor_review_plan_defaults_empty_subprocessor_list() -> None:
    plan = generate_third_party_llm_subprocessor_review_plan({"subprocessors": []})

    assert plan["schema_version"] == "max.spec.third_party_llm_subprocessor_review_plan.v1"
    assert plan["summary"]["subprocessor_count"] == 1
    assert plan["subprocessors"][0]["name"] == "proposed LLM subprocessor"
    assert plan["subprocessors"][0]["purpose"] == "LLM inference support"
    assert plan["contractual_risks"][0]["name"] == (
        "missing contractual controls for proposed LLM subprocessor"
    )
