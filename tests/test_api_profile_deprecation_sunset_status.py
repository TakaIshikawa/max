from __future__ import annotations

import json

from max.api import profile_deprecation_sunset_status_to_json


def test_profile_deprecation_sunset_status_covers_active_approaching_overdue_and_empty() -> None:
    empty = json.loads(profile_deprecation_sunset_status_to_json({"profiles": []}))
    assert empty["overall_status"] == "healthy"
    report = json.loads(profile_deprecation_sunset_status_to_json({"as_of": "2026-06-01T00:00:00Z", "warning_days": 10, "profiles": [{"profile": "active"}, {"profile": "soon", "sunset_at": "2026-06-05T00:00:00Z", "replacement": "next"}, {"profile": "overdue", "sunset_at": "2026-05-01T00:00:00Z", "replacement": "next"}, {"profile": "missing", "deprecated": True}]}))
    assert report["overall_status"] == "critical"
    assert report["approaching_sunset_count"] == 1
    assert report["overdue_sunset_count"] == 1
    assert report["missing_replacement_count"] == 1
