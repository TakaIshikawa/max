from __future__ import annotations

import json

from max.api import tact_daemon_publication_health_status_to_json


def test_tact_daemon_publication_health_status_handles_reachable_degraded_unreachable_and_never() -> None:
    report = json.loads(tact_daemon_publication_health_status_to_json({"as_of": "2026-06-01T12:00:00Z", "daemons": [{"daemon": "ok", "reachable": True, "last_successful_publish_at": "2026-06-01T11:00:00Z"}, {"daemon": "degraded", "reachable": True, "last_successful_publish_at": "2026-06-01T11:00:00Z", "pending_payload_count": 3}, {"daemon": "down", "reachable": False, "last_successful_publish_at": "2026-06-01T11:00:00Z"}, {"daemon": "new", "reachable": True}]}))
    assert report["overall_status"] == "critical"
    assert report["unreachable_count"] == 1
    assert report["pending_payload_count"] == 3
    assert {row["daemon"]: row["status"] for row in report["daemons"]}["new"] == "critical"
