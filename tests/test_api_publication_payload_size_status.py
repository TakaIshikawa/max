from __future__ import annotations

import json

from max.api import publication_payload_size_status_to_json


def test_publication_payload_size_status_supports_size_aliases_and_limits() -> None:
    data = json.loads(publication_payload_size_status_to_json({"limit_bytes": 100, "payloads": [{"publisher": "slack", "destination": "hook", "spec_id": "too-big", "payload_bytes": 120}, {"publisher": "jira", "destination": "issue", "spec_id": "warn", "size_bytes": 85}, {"publisher": "mail", "serialized_payload": "abc"}]}))

    assert [row["spec_id"] for row in data["rows"][:2]] == ["too-big", "warn"]
    assert data["summary"]["blocked_count"] == 1
    assert data["summary"]["warning_count"] == 1
    assert data["rows"][0]["recommended_action"] == "split_payload"


def test_publication_payload_size_status_reports_largest_payload_and_utilization() -> None:
    data = json.loads(publication_payload_size_status_to_json({"items": [{"id": "p", "payload_bytes": 50, "limit_bytes": 100}]}))

    assert data["summary"]["largest_payload_bytes"] == 50
    assert data["rows"][0]["utilization_ratio"] == 0.5
