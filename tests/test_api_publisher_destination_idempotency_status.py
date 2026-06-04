from __future__ import annotations

import json

from max.api import publisher_destination_idempotency_status_to_json


def test_publisher_destination_idempotency_status_groups_duplicates_and_conflicts() -> None:
    report = json.loads(publisher_destination_idempotency_status_to_json({"destinations": [{"destination": "slack", "key": "k1", "published_artifact_id": "a"}, {"destination": "slack", "idempotency_key": "k1", "published_artifact_id": "b"}, {"destination": "mail", "published_artifact_id": "c"}, {"destination": "web", "key": "k2", "duplicate_count": 1}]}))

    assert [row["destination"] for row in report["destination_rows"]] == ["slack", "web", "mail"]
    assert report["destination_rows"][0]["status"] == "critical"
    assert report["destination_rows"][2]["idempotency_key"] is None
    assert report["summary"]["duplicate_keys"] == 2
    assert report["summary"]["conflicting_keys"] == 1
