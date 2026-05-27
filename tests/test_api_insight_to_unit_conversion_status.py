from __future__ import annotations

import json

from max.api import insight_to_unit_conversion_status_to_json


def test_insight_to_unit_conversion_status_reports_blocked_and_rate() -> None:
    parsed = json.loads(insight_to_unit_conversion_status_to_json({"items": [{"id": "i2", "profile": "Ops", "domain": "Cost", "missing_inputs": ["evidence"], "reason": "Missing Evidence"}, {"insight_id": "i1", "profile": "Ops", "domain": "Cost", "unit_count": 2}]}))

    assert parsed["schema_version"] == "max.api.insight_to_unit_conversion_status.v1"
    assert parsed["summary"]["insight_count"] == 2
    assert parsed["summary"]["converted_count"] == 1
    assert parsed["summary"]["blocked_count"] == 1
    assert parsed["summary"]["conversion_rate"] == 0.5
    assert parsed["blocked_insights"][0]["insight_id"] == "i2"
    assert parsed["blocked_insights"][0]["blocker_reason"] == "missing_evidence"
