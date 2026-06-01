from __future__ import annotations

import json

from max.api import buildable_unit_spec_blocker_status_to_json


def test_buildable_unit_spec_blocker_status_no_blockers() -> None:
    report = json.loads(buildable_unit_spec_blocker_status_to_json({}))
    assert report["summary"]["health"] == "healthy"
    assert report["blocker_types"] == []


def test_buildable_unit_spec_blocker_status_approved_blocked_units() -> None:
    report = json.loads(buildable_unit_spec_blocker_status_to_json({"blockers": [{"id": "u1", "approved": True, "blocker_type": "missing_acceptance"}]}))
    assert report["summary"]["health"] == "critical"
    assert report["summary"]["approved_blocked_count"] == 1


def test_buildable_unit_spec_blocker_status_blocker_type_ranking() -> None:
    report = json.loads(buildable_unit_spec_blocker_status_to_json({"blockers": [{"blocker_type": "b"}, {"blocker_type": "a"}, {"blocker_type": "a"}]}))
    assert report["blocker_types"][0] == {"blocker_type": "a", "count": 2}


def test_buildable_unit_spec_blocker_status_age_bucket_aggregation() -> None:
    report = json.loads(buildable_unit_spec_blocker_status_to_json({"blockers": [{"created_at": "2026-05-31T00:00:00Z"}, {"created_at": "2026-05-01T00:00:00Z"}]}, as_of="2026-06-01T00:00:00Z"))
    assert {row["age_bucket"] for row in report["age_buckets"]} == {"0_1d", "over_30d"}
