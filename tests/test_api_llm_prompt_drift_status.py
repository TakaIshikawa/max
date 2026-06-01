from __future__ import annotations

import json

from max.api import llm_prompt_drift_status_to_json


def test_llm_prompt_drift_status_reports_mismatch_ratio_and_families() -> None:
    report = json.loads(llm_prompt_drift_status_to_json({"critical_mismatch_ratio": 0.5, "prompts": [{"prompt_id": "a", "family": "sales", "active_version": "v1", "expected_version": "v2"}, {"prompt_id": "b", "family": "sales", "active_version": "v2", "expected_version": "v2"}]}))

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["mismatch_ratio"] == 0.5
    assert report["stale_versions"][0]["prompt_id"] == "a"
    assert report["families"][0]["mismatched_prompts"] == 1


def test_llm_prompt_drift_status_no_prompts_is_healthy() -> None:
    report = json.loads(llm_prompt_drift_status_to_json({}))

    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["mismatch_ratio"] == 0.0
