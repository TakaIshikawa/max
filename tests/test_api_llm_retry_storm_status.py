from __future__ import annotations

import json

from max.api import llm_retry_storm_status_to_json


def test_llm_retry_storm_status_supports_aliases_and_flags_storms() -> None:
    data = json.loads(llm_retry_storm_status_to_json({"retry_rate_threshold": 0.2, "retry_count_threshold": 5, "attempts": [{"provider": "openai", "model": "m1", "failures": 6, "total_requests": 20}, {"provider": "anthropic", "model": "m2", "retry_count": 1, "attempts": 20}]}))

    assert [row["provider"] for row in data["rows"]] == ["openai", "anthropic"]
    assert data["summary"]["storm_count"] == 1
    assert data["rows"][0]["recommended_action"] == "failover_or_throttle"


def test_llm_retry_storm_status_summary_counts_providers_and_retries() -> None:
    data = json.loads(llm_retry_storm_status_to_json({"items": [{"provider": "p", "retries": 2}, {"provider": "p", "retry_count": 3}]}))

    assert data["summary"]["provider_count"] == 1
    assert data["summary"]["retry_attempt_count"] == 5
