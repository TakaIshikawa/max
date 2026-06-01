from __future__ import annotations

import json

from max.api import publisher_destination_quota_status_to_json


def test_publisher_destination_quota_status_unlimited_destinations() -> None:
    report = json.loads(publisher_destination_quota_status_to_json({"destinations": [{"destination": "slack", "unlimited": True, "used_quota": 999}]}))
    assert report["summary"]["status"] == "healthy"
    assert report["destinations"][0]["remaining_quota"] is None


def test_publisher_destination_quota_status_exhausted_required_destination() -> None:
    report = json.loads(publisher_destination_quota_status_to_json({"destinations": [{"destination": "jira", "quota_limit": 10, "used_quota": 10, "required": True}]}))
    assert report["summary"]["status"] == "critical"
    assert report["exhausted_destinations"][0]["destination"] == "jira"


def test_publisher_destination_quota_status_sorted_lowest_remaining() -> None:
    report = json.loads(publisher_destination_quota_status_to_json({"destinations": [{"destination": "b", "quota_limit": 100, "used_quota": 50}, {"destination": "a", "quota_limit": 100, "used_quota": 95}]}))
    assert [row["destination"] for row in report["destinations"]] == ["a", "b"]


def test_publisher_destination_quota_status_missing_reset_time() -> None:
    report = json.loads(publisher_destination_quota_status_to_json({"destinations": [{"destination": "email", "quota_limit": 100, "used_quota": 10}]}))
    assert report["destinations"][0]["reset_at"] is None
    assert report["summary"]["status"] == "healthy"

