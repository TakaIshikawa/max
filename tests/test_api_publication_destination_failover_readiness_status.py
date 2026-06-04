from __future__ import annotations

import json

from max.api.publication_destination_failover_readiness_status import publication_destination_failover_readiness_status_to_json


def test_publication_destination_failover_readiness_status_sorts_and_classifies() -> None:
    parsed = json.loads(
        publication_destination_failover_readiness_status_to_json(
            {
                "destinations": [
                    {"destination": "ok", "primary_available": True, "fallback_available": True, "queued_publications": 9},
                    {"destination": "stale", "primary_available": True, "fallback_available": True, "failover_drill_age_days": 45},
                    {"destination": "down", "primary_available": "false", "fallback_available": "no", "queued_publications": 3},
                    {"destination": "fallback", "primary_available": False, "fallback_available": "yes", "queued_publications": 10},
                ]
            },
            max_drill_age_days=30,
        )
    )

    assert parsed["status"] == "critical"
    assert [row["destination"] for row in parsed["destinations"]] == ["down", "fallback", "stale", "ok"]
    assert [row["status"] for row in parsed["destinations"]] == ["critical", "warning", "warning", "ok"]
    assert parsed["destinations"][0]["primary_available"] is False
    assert parsed["summary"]["warning_destination_count"] == 2


def test_publication_destination_failover_readiness_status_empty_and_fallback_names() -> None:
    empty = json.loads(publication_destination_failover_readiness_status_to_json({}))
    assert empty["summary"] == {
        "critical_destination_count": 0,
        "destination_count": 0,
        "queued_publication_count": 0,
        "status": "ok",
        "warning_destination_count": 0,
    }
    assert empty["destinations"] == []

    parsed = json.loads(publication_destination_failover_readiness_status_to_json({"items": [{}]}))
    assert parsed["destinations"][0]["destination"] == "destination-1"
