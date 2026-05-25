from __future__ import annotations

import json

from max.spec.llm_cost_spike_response_plan import generate_llm_cost_spike_response_plan


def test_llm_cost_spike_response_plan_handles_token_spike() -> None:
    plan = generate_llm_cost_spike_response_plan(
        {
            "metadata": {
                "llm_cost_spike_response": {
                    "spike_type": "token",
                    "baseline": "last 14 day p50",
                    "thresholds": [{"metric": "tokens", "threshold": "2x baseline"}],
                }
            }
        }
    )

    assert plan["trigger_thresholds"][0]["metric"] == "tokens"
    assert "max tokens" in plan["containment_actions"][0]["name"]
    assert plan["risks"] == []


def test_llm_cost_spike_response_plan_handles_price_spike() -> None:
    plan = generate_llm_cost_spike_response_plan(
        {
            "metadata": {
                "llm_cost_spike_response": {
                    "spike_type": "price",
                    "baseline": "approved price book",
                }
            }
        }
    )

    assert "lower-cost model" in plan["containment_actions"][0]["name"]
    assert "price book" in plan["containment_actions"][0]["name"]


def test_llm_cost_spike_response_plan_flags_missing_baseline() -> None:
    plan = generate_llm_cost_spike_response_plan(
        {"metadata": {"llm_cost_spike_response": {"thresholds": ["daily spend > 500 usd"]}}}
    )

    assert plan["risks"][0]["name"] == "missing cost baseline"
    assert plan["risks"][0]["severity"] == "high"


def test_llm_cost_spike_response_plan_accepts_containment_actions() -> None:
    plan = generate_llm_cost_spike_response_plan(
        {
            "metadata": {
                "llm_cost_spike_response": {
                    "baseline": "budget forecast",
                    "containment": ["disable batch summarization"],
                    "models": [{"model": "gpt-costly", "stage": "evaluation"}],
                }
            }
        }
    )

    assert plan["containment_actions"][0]["name"] == "disable batch summarization"
    assert plan["affected_surfaces"][0]["model"] == "gpt-costly"


def test_llm_cost_spike_response_plan_is_deterministic_and_preserves_metadata() -> None:
    payload = {
        "source": {"idea_id": "cost-1"},
        "metadata": {
            "llm_cost_spike_response": {
                "baseline": "weekly budget",
                "triggers": [{"metric": "z"}, {"metric": "a"}, {"metric": "a"}],
            }
        },
    }

    first = generate_llm_cost_spike_response_plan(payload)
    assert first == generate_llm_cost_spike_response_plan(payload)
    assert [row["name"] for row in first["trigger_thresholds"]] == ["a", "z"]
    assert first["source"]["idea_id"] == "cost-1"
    assert json.loads(json.dumps(first)) == first
