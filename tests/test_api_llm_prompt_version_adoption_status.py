from __future__ import annotations

import json

from max.api import llm_prompt_version_adoption_status_to_json


def test_llm_prompt_version_adoption_status_sums_versions_and_flags_legacy_share() -> None:
    data = json.loads(llm_prompt_version_adoption_status_to_json({"warning_legacy_share": 0.1, "critical_legacy_share": 0.25, "prompts": [{"prompt_name": "ranker", "current_version": "v1", "latest_version": "v2", "observed_versions": {"v1": 30, "v2": 70}}, {"prompt_name": "writer", "latest_version": "v3", "observed_versions": {"v3": 100}}]}))

    assert data["status"] == "critical"
    assert data["summary"]["prompt_count"] == 2
    assert data["summary"]["lagging_prompt_count"] == 1
    assert data["summary"]["legacy_request_count"] == 30
    assert data["summary"]["total_request_count"] == 200
    assert data["summary"]["adoption_percentage"] == 85.0
    assert data["prompts"][0]["prompt_name"] == "ranker"
    assert data["prompts"][0]["legacy_request_share"] == 0.3
