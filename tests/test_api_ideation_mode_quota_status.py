from __future__ import annotations

import json

from max.api import ideation_mode_quota_status_to_json


def test_ideation_mode_quota_status_accepts_aliases_and_sorts_by_pressure() -> None:
    parsed = json.loads(ideation_mode_quota_status_to_json({"quotas": [{"mode": "direct", "quota": 10, "used": 11}, {"name": "refinement", "limit": 5, "usage": 5}, {"mode": "cross domain", "capacity": 10, "actual": 3}]}))

    assert parsed["schema_version"] == "max.api.ideation_mode_quota_status.v1"
    assert [row["mode"] for row in parsed["modes"]] == ["direct", "refinement", "cross_domain"]
    assert parsed["modes"][0]["remaining"] == 0
    assert parsed["summary"]["over_quota_count"] == 1
    assert parsed["summary"]["exhausted_count"] == 1
