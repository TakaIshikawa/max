from __future__ import annotations

import json

from max.api import prompt_template_version_drift_status_to_json


def test_prompt_template_version_drift_status_classifies_versions() -> None:
    parsed = json.loads(prompt_template_version_drift_status_to_json({"templates": [{"template_id": "ok", "deployed_version": "1", "approved_version": "1"}, {"template_id": "missing", "deployed_version": "2", "drift_days": 3}, {"template_id": "stale", "deployed_version": "3", "approved_version": "2", "drift_days": 40}]}))

    assert [row["template_id"] for row in parsed["templates"]] == ["stale", "missing", "ok"]
    assert parsed["templates"][0]["status"] == "critical"
    assert parsed["templates"][1]["status"] == "high"
    assert parsed["summary"]["template_count"] == 3
    assert parsed["summary"]["drifted_count"] == 2
    assert parsed["summary"]["critical_count"] == 1
