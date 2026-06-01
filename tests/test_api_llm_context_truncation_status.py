from __future__ import annotations

import json

from max.api import llm_context_truncation_status_to_json


def test_llm_context_truncation_status_reports_affected_prompts_by_model() -> None:
    report = json.loads(llm_context_truncation_status_to_json({"critical_truncation_rate": 0.2, "prompts": [{"prompt_id": "p1", "model": "gpt-a", "input_tokens": 1000, "token_limit": 800, "truncated_tokens": 250}, {"prompt_id": "p2", "model": "gpt-b", "input_tokens": 1000, "token_limit": 900, "truncated_tokens": 60}]}))

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["affected_prompt_count"] == 2
    assert report["summary"]["worst_model"] == "gpt-a"
    assert report["prompts"][0]["prompt_id"] == "p1"
    assert report["prompts"][0]["truncation_rate"] == 0.25


def test_llm_context_truncation_status_clamps_negative_values() -> None:
    report = json.loads(llm_context_truncation_status_to_json({"prompts": [{"id": "p", "input_tokens": -10, "truncated_tokens": -2}]}))

    assert report["prompts"][0]["input_tokens"] == 0
    assert report["prompts"][0]["truncation_rate"] == 0.0
