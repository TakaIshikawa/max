from __future__ import annotations

import json

from max.api.llm_rate_limit_queue_status import llm_rate_limit_queue_status_to_json


def test_llm_rate_limit_queue_status_accepts_mapping_and_classifies() -> None:
    report = json.loads(llm_rate_limit_queue_status_to_json({"queues": {"openai": {"model": "gpt-5", "queued_requests": 3, "retry_after_seconds": 300}, "anthropic": {"queued_requests": 2, "oldest_wait_seconds": 90}, "local": {"queued_requests": 0, "retry_after_seconds": 999}}}, warning_wait_seconds=60, critical_wait_seconds=300))

    assert [row["provider"] for row in report["queue_rows"]] == ["openai", "anthropic", "local"]
    assert [row["status"] for row in report["queue_rows"]] == ["critical", "warning", "ok"]
    assert report["queue_rows"][1]["model"] == "all"
    assert report["queue_rows"][2]["effective_wait_seconds"] == 0


def test_llm_rate_limit_queue_status_accepts_list() -> None:
    report = json.loads(llm_rate_limit_queue_status_to_json({"queues": [{"provider": "openrouter", "model": "all", "queued_requests": 1, "oldest_wait_seconds": 10}]}))

    assert report["queue_rows"][0]["status"] == "ok"
