from __future__ import annotations

import json

from max.api import publication_webhook_delivery_status_to_json


def test_publication_webhook_delivery_status_flags_failing_destinations() -> None:
    report = json.loads(publication_webhook_delivery_status_to_json({"destinations": [{"destination": "ok", "delivered_count": 10, "failed_count": 0, "retry_pending_count": 0}, {"destination": "retry", "delivered_count": 8, "failed_count": 2, "retry_pending_count": 5}, {"destination": "fail", "delivered_count": 1, "failed_count": 1, "retry_pending_count": 0}]}))

    assert [row["destination"] for row in report["rows"]] == ["retry", "fail", "ok"]
    assert report["failing_destinations"][0]["next_action"] == "drain retries"
    assert report["summary"]["delivery_failure_ratio"] == 0.1364
