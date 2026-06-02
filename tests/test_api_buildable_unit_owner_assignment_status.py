from __future__ import annotations

import json

from max.api import buildable_unit_owner_assignment_status_to_json


def test_owner_assignment_distinguishes_pending_and_approved_high_priority() -> None:
    report = json.loads(buildable_unit_owner_assignment_status_to_json({"units": [{"unit_id": "a", "profile": "core", "status": "approved", "priority": "high"}, {"unit_id": "b", "profile": "core", "status": "pending"}, {"unit_id": "c", "profile": "growth", "status": "approved", "owner": "ann"}]}))

    assert report["status"] == "critical"
    assert report["summary"]["unassigned_approved_count"] == 1
    assert report["summary"]["unassigned_pending_count"] == 1
    assert report["summary"]["high_priority_unassigned_approved_count"] == 1
