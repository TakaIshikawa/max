from __future__ import annotations

import json

from max.api import tact_daemon_connectivity_status_to_json


def test_tact_daemon_connectivity_reports_unreachable_and_latency() -> None:
    report = json.loads(tact_daemon_connectivity_status_to_json({"targets": [{"target": "prod", "reachable": False, "last_error": "timeout"}, {"target": "stage", "reachable": True, "latency_ms": 700, "last_success_at": "2026-05-31T11:00:00Z"}]}, now="2026-05-31T12:00:00Z", latency_warn_ms=500))

    assert report["summary"]["severity"] == "critical"
    assert report["targets"][0]["target"] == "prod"
    assert report["targets"][0]["last_error"] == "timeout"
    assert report["targets"][1]["severity"] == "warn"


def test_tact_daemon_connectivity_empty_is_ok() -> None:
    report = json.loads(tact_daemon_connectivity_status_to_json({}, now="2026-05-31T00:00:00Z"))

    assert report["summary"]["severity"] == "ok"
