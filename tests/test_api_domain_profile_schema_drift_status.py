from __future__ import annotations

import json

from max.api import domain_profile_schema_drift_status_to_json


def test_domain_profile_schema_drift_status_identifies_profile_states() -> None:
    report = json.loads(domain_profile_schema_drift_status_to_json({"current_schema_version": "v3", "profiles": [{"profile": "current", "schema_version": "v3"}, {"profile": "old", "schema_version": "v2"}, {"profile": "invalid", "schema_version": "v3", "missing_required_fields": ["name"]}, {"profile": "unknown"}]}))
    statuses = {row["profile"]: row["status"] for row in report["profiles"]}
    assert report["overall_status"] == "critical"
    assert statuses["current"] == "healthy"
    assert statuses["old"] == "warning"
    assert statuses["invalid"] == "critical"
    assert statuses["unknown"] == "critical"
