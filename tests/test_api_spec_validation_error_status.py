from __future__ import annotations

import json

from max.api.spec_validation_error_status import spec_validation_error_status_to_json


def test_spec_validation_error_status_groups_by_severity_and_error_code() -> None:
    report = json.loads(
        spec_validation_error_status_to_json(
            {
                "errors": [
                    {"spec_id": "s1", "profile": "p", "field": "title", "error_code": "required", "severity": "critical", "first_seen_at": "2026-05-27T00:00:00Z"},
                    {"spec_id": "s1", "profile": "p", "field": "body", "error_code": "required", "severity": "high", "first_seen_at": "2026-05-27T00:00:00Z"},
                    {"spec_id": "s2", "profile": "p", "field": "body", "error_code": "format", "severity": "low", "first_seen_at": "2026-05-27T00:00:00Z"},
                ]
            }
        )
    )

    assert report["summary"]["affected_specs"] == 2
    assert report["summary"]["total_errors"] == 3
    assert report["summary"]["critical_errors"] == 1
    assert report["summary"]["top_error_codes"][0] == {"error_code": "required", "count": 2}
    assert report["rows"][0]["spec_id"] == "s1"
    assert report["severity_counts"]["critical"] == 1
