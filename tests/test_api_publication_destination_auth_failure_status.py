from __future__ import annotations

import json

from max.api.publication_destination_auth_failure_status import publication_destination_auth_failure_status_to_json


def test_publication_destination_auth_failure_status_accepts_mapping_and_classifies() -> None:
    report = json.loads(publication_destination_auth_failure_status_to_json({"destinations": {"slack": {"recent_auth_failures": 3, "last_failure_at": "2026-06-01T00:00:00Z", "remediation_hint": "rotate token"}, "email": {"recent_auth_failures": 1}, "rss": {"recent_auth_failures": 0}}}))

    assert [row["destination"] for row in report["destination_rows"]] == ["slack", "email", "rss"]
    assert report["destination_rows"][0]["remediation_hint"] == "rotate token"
    assert [row["status"] for row in report["destination_rows"]] == ["critical", "warning", "ok"]


def test_publication_destination_auth_failure_status_accepts_list_and_successful_check() -> None:
    report = json.loads(publication_destination_auth_failure_status_to_json({"destinations": [{"destination": "webhook", "auth_failures": 0, "successful_recent_check": True, "last_failure_at": "old"}]}))

    assert report["destination_rows"][0]["status"] == "ok"
    assert report["destination_rows"][0]["last_failure_at"] == "old"
