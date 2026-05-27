from __future__ import annotations

import json

from max.api.publication_idempotency_status import publication_idempotency_status_to_json


def test_publication_idempotency_status_detects_duplicates_collisions_and_sorts() -> None:
    report = json.loads(publication_idempotency_status_to_json({"attempts": [{"destination": "slack", "idempotency_key": "k2", "attempt_count": 1, "duplicate_count": 1}, {"destination": "email", "idempotency_key": "k1", "attempt_count": 3, "duplicate_count": 0, "external_ids": ["a", "b"]}, {"destination": "web", "idempotency_key": "k3", "attempt_count": "bad", "duplicate_count": 0}]}))

    assert [row["destination"] for row in report["rows"]] == ["email", "slack", "web"]
    assert report["summary"]["total_attempts"] == 4
    assert report["summary"]["duplicate_count"] == 1
    assert report["summary"]["collision_count"] == 2
    assert report["summary"]["affected_destinations"] == ["email", "slack"]
    assert json.loads(json.dumps(report, sort_keys=True)) == report
