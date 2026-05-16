from __future__ import annotations

from max.spec.ai_usage_policy import generate_ai_usage_policy


def test_ai_usage_policy_covers_required_sections_and_strict_controls() -> None:
    policy = generate_ai_usage_policy(
        {
            "project": {"title": "Claims Triage"},
            "ai": {
                "approved_use_cases": ["summarization", "routing"],
                "data_types": ["PII"],
                "domain": "regulated finance",
                "automated_decisions": True,
                "vendor_constraints": ["no training on customer data"],
            },
            "evidence": {"source_idea_ids": ["ai-1"]},
        }
    )

    assert policy["kind"] == "max.ai_usage_policy"
    assert policy["summary"]["control_level"] == "strict"
    assert policy["human_review"]["required"] is True
    assert "regulated personal data" in policy["prohibited_data"]
    assert policy["vendor_constraints"] == ["no training on customer data"]
    assert policy["evidence"] == ["source_idea:ai-1"]


def test_ai_usage_policy_defaults_missing_fields() -> None:
    policy = generate_ai_usage_policy({})

    assert policy["summary"]["title"] == "Unknown"
    assert policy["summary"]["control_level"] == "standard"
    assert policy["approved_use_cases"] == ["Unknown"]
    assert policy["human_review"]["required"] is False
    assert policy["policy_exceptions"]["allowed"] is True


def test_ai_usage_policy_is_deterministic() -> None:
    payload = {"ai": {"approved_use_cases": ["z", "a", "z"]}}

    assert generate_ai_usage_policy(payload) == generate_ai_usage_policy(payload)
    assert generate_ai_usage_policy(payload)["approved_use_cases"] == ["a", "z"]
