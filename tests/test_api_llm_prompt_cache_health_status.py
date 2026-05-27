from __future__ import annotations

import json

from max.api import llm_prompt_cache_health_status_to_json


def test_llm_prompt_cache_health_status_sorts_low_hit_rate_first() -> None:
    parsed = json.loads(llm_prompt_cache_health_status_to_json({"metrics": [{"provider": "a", "model": "m1", "hits": 1, "misses": 9, "stale_entries": 2, "saved_tokens": 10}, {"provider": "b", "model": "m2", "cache_hits": 8, "cache_misses": 2}]}))

    assert parsed["schema_version"] == "max.api.llm_prompt_cache_health_status.v1"
    assert [row["provider"] for row in parsed["caches"]] == ["a", "b"]
    assert parsed["summary"]["request_count"] == 20
    assert parsed["summary"]["hit_rate"] == 0.45
    assert parsed["summary"]["stale_entry_count"] == 2
