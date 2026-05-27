from __future__ import annotations

import json

from max.api import profile_source_budget_status_to_json


def test_profile_source_budget_status_clamps_usage_and_groups_sources() -> None:
    parsed = json.loads(profile_source_budget_status_to_json({"items": [{"profile": "P1", "source": "docs", "budget": 100, "used": 120, "unit": "tokens"}, {"profile": "P2", "source": "docs", "limit": 100, "spent": 85}]}))

    assert parsed["schema_version"] == "max.api.profile_source_budget_status.v1"
    assert [row["status"] for row in parsed["budgets"]] == ["exhausted", "near_limit"]
    assert parsed["budgets"][0]["usage_ratio"] == 1.0
    assert parsed["summary"]["profile_count"] == 2
    assert parsed["summary"]["source_count"] == 1
