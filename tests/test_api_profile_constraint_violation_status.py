from __future__ import annotations

import json

from max.api import profile_constraint_violation_status_to_json


def test_profile_constraint_violation_status_escalates_blocking() -> None:
    report = json.loads(profile_constraint_violation_status_to_json({"violations": [{"id": "v1", "profile": "core", "constraint_type": "quota", "blocking": True}, {"id": "v2", "profile": "core", "constraint_type": "quota"}]}))

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["blocking_count"] == 1
    assert report["summary"]["repeated_constraint_types"] == [{"constraint_type": "quota", "count": 2}]
    assert report["blocking_violations"][0]["violation_id"] == "v1"


def test_profile_constraint_violation_status_defaults_unknown_profile() -> None:
    report = json.loads(profile_constraint_violation_status_to_json({"violations": [{"constraint_type": "tone"}]}))

    assert report["summary"]["status"] == "warning"
    assert report["profiles"][0]["profile"] == "unknown_profile"
