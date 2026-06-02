from __future__ import annotations

import json

from max.api import llm_prompt_cache_utilization_status_to_json


def test_prompt_cache_utilization_reports_rates_and_no_activity() -> None:
    report = json.loads(llm_prompt_cache_utilization_status_to_json({"families": [{"prompt_family": "draft", "cache_hits": 9, "cache_misses": 1, "tokens_saved": 100}, {"prompt_family": "cold", "cache_hits": 1, "cache_misses": 9}, {"prompt_family": "empty"}]}))

    assert report["summary"]["hit_rate"] == 0.5
    assert report["summary"]["avoided_tokens"] == 100
    assert {row["prompt_family"]: row["status"] for row in report["families"]}["empty"] == "no_activity"
    assert {row["prompt_family"]: row["hit_rate"] for row in report["families"]}["draft"] == 0.9
