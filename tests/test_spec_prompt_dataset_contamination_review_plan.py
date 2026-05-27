from __future__ import annotations

import json

from max.spec.prompt_dataset_contamination_review_plan import (
    generate_prompt_dataset_contamination_review_plan,
)


def test_prompt_dataset_contamination_review_plan_covers_required_sections() -> None:
    plan = generate_prompt_dataset_contamination_review_plan(
        {
            "metadata": {
                "prompt_dataset_contamination_review": {
                    "contamination_summary": [
                        {
                            "dataset": "jailbreak-eval-v4",
                            "contamination_source": "training dump",
                            "indicator": "exact prompt overlap",
                        }
                    ],
                    "affected_examples": [
                        {
                            "prompt_id": "p-100",
                            "dataset": "jailbreak-eval-v4",
                            "contamination_source": "training dump",
                        }
                    ],
                    "quarantine_steps": ["disable contaminated eval slice"],
                    "replacement_sampling_plan": [{"dataset": "jailbreak-eval-v5", "sample_size": "250"}],
                    "approval_gates": [{"reviewer": "Safety Lead", "decision": "approve replacement"}],
                    "audit_evidence": [{"artifact": "quarantine log", "location": "s3://audit/prompt"}],
                    "reviewers": [{"reviewer": "Safety Lead", "role": "policy reviewer"}],
                }
            }
        }
    )

    assert plan["title"] == "Prompt Dataset Contamination Review Plan"
    assert set(plan) >= {
        "contamination_summary",
        "affected_examples",
        "quarantine_steps",
        "replacement_sampling_plan",
        "approval_gates",
        "audit_evidence",
    }
    assert plan["contamination_summary"][0]["dataset"] == "jailbreak-eval-v4"
    assert plan["contamination_summary"][0]["contamination_source"] == "training dump"
    assert plan["affected_examples"][0]["prompt_id"] == "p-100"
    assert plan["affected_examples"][0]["dataset"] == "jailbreak-eval-v4"
    assert plan["reviewers"][0]["reviewer"] == "Safety Lead"
    assert plan["audit_evidence"][0]["artifact"] == "quarantine log"


def test_prompt_dataset_contamination_review_plan_defaults_are_deterministic_and_json_safe() -> None:
    plan = generate_prompt_dataset_contamination_review_plan({})

    assert plan == generate_prompt_dataset_contamination_review_plan({})
    assert plan["schema_version"] == "max.spec.prompt_dataset_contamination_review_plan.v1"
    assert plan["summary"]["affected_example_count"] == 1
    assert plan["affected_examples"][0]["name"] == "suspect prompt example"
    assert plan["reviewers"][0]["name"] == "evaluation owner"
    assert json.loads(json.dumps(plan)) == plan
