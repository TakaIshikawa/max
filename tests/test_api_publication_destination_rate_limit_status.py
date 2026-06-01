from __future__ import annotations

import json

from max.api import publication_destination_rate_limit_status_to_json


def test_publication_destination_rate_limit_status_sorts_by_exhaustion() -> None:
    report = json.loads(publication_destination_rate_limit_status_to_json({"destinations": [{"destination": "blog", "limit": 100, "remaining": 70}, {"destination": "mail", "limit": 100, "remaining": 0, "reset_at": "2026-06-01T00:00:00Z"}, {"destination": "social", "limit": 100, "remaining": 5}]}))

    assert [row["destination"] for row in report["destinations"]] == ["mail", "social", "blog"]
    assert report["summary"]["status"] == "critical"
    assert report["blocked_destinations"][0]["destination"] == "mail"
    assert report["next_reset"] == "2026-06-01T00:00:00Z"


def test_publication_destination_rate_limit_status_empty_is_no_data() -> None:
    report = json.loads(publication_destination_rate_limit_status_to_json({}))

    assert report["summary"]["status"] == "no_data"
