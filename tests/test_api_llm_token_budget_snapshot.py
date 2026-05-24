from __future__ import annotations

import json

from max.api.llm_token_budget_snapshot import llm_token_budget_snapshot_to_json


def test_llm_token_budget_snapshot_aggregates_costs_and_tokens() -> None:
    parsed = json.loads(
        llm_token_budget_snapshot_to_json(
            {
                "usage": [
                    {"consumer": "rank", "model": "GPT 4.1", "prompt_tokens": 1000, "completion_tokens": 500},
                    {"consumer": "draft", "model": "gpt-4.1", "input_tokens": 500, "output_tokens": 500},
                ],
                "pricing": {"gpt-4.1": {"prompt": 0.01, "completion": 0.02}},
                "soft_limit": 0.03,
                "hard_limit": 0.04,
            }
        )
    )

    assert parsed["summary"]["total_tokens"] == 2500
    assert parsed["summary"]["estimated_cost"] == 0.035
    assert parsed["summary"]["budget_status"] == "soft_limit_exceeded"
    assert parsed["model_usage"][0]["model"] == "gpt-4.1"


def test_llm_token_budget_snapshot_hard_limit_and_unknown_pricing() -> None:
    parsed = json.loads(llm_token_budget_snapshot_to_json({"entries": [{"stage": "s", "model_name": "mystery", "prompt_tokens": 100}], "budget": 0}))

    assert parsed["unknown_cost_entries"][0]["model"] == "mystery"
    assert parsed["summary"]["budget_status"] == "within_budget"


def test_llm_token_budget_snapshot_top_consumers_sorting() -> None:
    parsed = json.loads(
        llm_token_budget_snapshot_to_json(
            {
                "usage": [{"consumer": "small", "model": "m", "prompt_tokens": 1}, {"consumer": "large", "model": "m", "prompt_tokens": 20}],
                "prices": {"m": 1},
                "metadata": {"run": "r1"},
            },
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert [row["consumer"] for row in parsed["top_consumers"]] == ["large", "small"]
    assert parsed["metadata"]["run"] == "r1"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
