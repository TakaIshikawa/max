from __future__ import annotations

import json

from max.api import buildable_unit_graduation_criteria_status_to_json


def test_buildable_unit_graduation_criteria_status_summarizes_readiness_and_blockers() -> None:
    report = json.loads(buildable_unit_graduation_criteria_status_to_json({"units": [{"unit_id": "ready"}, {"unit_id": "blocked", "missing_evidence": ["trace"], "unmet_gates": ["qa"]}, {"unit_id": "review", "required_signoffs": ["lead"]}, {"unit_id": "rejected", "decision": "rejected"}]}))
    assert report["overall_status"] == "blocked"
    assert report["summary"] == {"blocked_count": 1, "ready_count": 1, "rejected_count": 1, "review_needed_count": 1, "total_units": 4}
    assert report["blockers"][0]["unit_id"] == "blocked"
