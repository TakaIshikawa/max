from __future__ import annotations

import json

from max.api import source_api_deprecation_status_to_json as exported
from max.api.source_api_deprecation_status import source_api_deprecation_status_to_json


def test_source_api_deprecation_status_handles_current_endpoints() -> None:
    report = json.loads(source_api_deprecation_status_to_json([{"adapter": "rss", "endpoint": "/v2", "deprecated": False}], as_of="2026-01-01T00:00:00Z"))

    assert exported is source_api_deprecation_status_to_json
    assert report["endpoints"][0]["status"] == "current"
    assert report["summary"]["status"] == "current"


def test_source_api_deprecation_status_computes_days_until_sunset() -> None:
    report = json.loads(source_api_deprecation_status_to_json([{"adapter": "crm", "endpoint": "/v1", "deprecated": True, "replacement": "/v2", "sunset_at": "2026-01-21T00:00:00Z", "profiles": ["a", "b"]}], as_of="2026-01-01T00:00:00Z", urgent_days=10))

    assert report["endpoints"][0]["days_until_sunset"] == 20
    assert report["endpoints"][0]["replacement_available"] is True
    assert report["endpoints"][0]["impacted_profile_count"] == 2
    assert report["endpoints"][0]["status"] == "watch"


def test_source_api_deprecation_status_marks_no_replacement_urgent() -> None:
    report = json.loads(source_api_deprecation_status_to_json({"endpoints": [{"adapter": "legacy", "endpoint": "/v1", "is_deprecated": True, "profile": "core"}]}, as_of="2026-01-01T00:00:00Z"))

    assert report["endpoints"][0]["status"] == "urgent"
    assert report["summary"]["status"] == "urgent"
