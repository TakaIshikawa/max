from __future__ import annotations

import json

from max.api.spec_acceptance_criteria_coverage_status import spec_acceptance_criteria_coverage_status_to_json


def test_spec_acceptance_criteria_coverage_status_computes_and_sorts() -> None:
    report = json.loads(spec_acceptance_criteria_coverage_status_to_json({"specs": [{"spec_id": "ok", "criteria_count": 4, "testable_criteria_count": 4, "target_coverage_ratio": 0.8}, {"spec_id": "low", "criteria_count": 10, "testable_criteria_count": 3, "target_coverage_ratio": 0.7}, {"spec_id": "empty", "criteria_count": 0, "testable_criteria_count": "bad"}]}))

    assert [row["spec_id"] for row in report["rows"]] == ["low", "empty", "ok"]
    assert report["rows"][0]["coverage_ratio"] == 0.3
    assert report["rows"][0]["undercovered"] is True
    assert report["summary"]["spec_count"] == 3
    assert report["summary"]["total_criteria"] == 14
    assert report["summary"]["total_testable_criteria"] == 7
    assert report["summary"]["undercovered_count"] == 1
