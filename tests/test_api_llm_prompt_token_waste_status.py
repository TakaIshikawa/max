from __future__ import annotations

import json

from max.api import llm_prompt_token_waste_status_to_json


def test_llm_prompt_token_waste_status_coerces_tokens_and_sorts() -> None:
    report = json.loads(llm_prompt_token_waste_status_to_json({"prompts": [{"prompt_name": "ok", "input_tokens": 800, "output_tokens": 100, "max_context_tokens": 1000, "failure_count": 0, "run_count": 5}, {"name": "warn", "input_tokens": 10, "output_tokens": 10, "max_context_tokens": 1000}, {"prompt_name": "crit", "input_tokens": -5, "output_tokens": "bad", "max_context_tokens": 100, "failure_count": 3, "run_count": 5}]}))

    assert [row["prompt_name"] for row in report["prompt_rows"]] == ["crit", "warn", "ok"]
    assert report["prompt_rows"][0]["failure_rate"] == 0.6
    assert report["prompt_rows"][0]["input_tokens"] == 0
    assert report["summary"]["total_wasted_context_tokens"] == 1180
