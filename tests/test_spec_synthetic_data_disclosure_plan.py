from __future__ import annotations

from max.spec.synthetic_data_disclosure_plan import generate_synthetic_data_disclosure_plan


def test_synthetic_data_disclosure_renders_required_sections() -> None:
    plan = generate_synthetic_data_disclosure_plan({"metadata": {"synthetic_data_disclosure": {"datasets": [{"dataset": "tickets-synth", "generation_method": "llm rewrite", "source_data_class": "support"}]}}})
    assert plan["generation_method"][0]["generation_method"] == "llm rewrite"
    assert plan["source_constraints"] and plan["privacy_review"] and plan["downstream_labeling"] and plan["customer_disclosure"]


def test_synthetic_data_disclosure_high_risk_requires_approval() -> None:
    plan = generate_synthetic_data_disclosure_plan({"metadata": {"synthetic_data_disclosure": {"generated_datasets": [{"name": "pii-synth", "source_data_class": "customer pii"}]}}})
    assert plan["privacy_review"][0]["severity"] == "high"
    assert "explicit privacy review and approval" in plan["approval_actions"][0]["description"]


def test_synthetic_data_disclosure_empty_input_defaults_unknowns() -> None:
    plan = generate_synthetic_data_disclosure_plan({})
    assert plan["generation_method"][0]["generation_method"] == "unknown"
